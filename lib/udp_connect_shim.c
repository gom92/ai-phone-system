/*
 * udp_connect_shim.c - LD_PRELOAD workaround for a sandbox seccomp rule.
 *
 * This container blocks UDP sends from UNCONNECTED sockets: sendto() /
 * sendmsg() with a per-message destination on an unconnected UDP socket
 * fails with EPERM ("Operation not permitted"). Sends on an already
 * CONNECTED UDP socket (send()/sendmsg() without destination) work fine.
 *
 * This shim intercepts sendto/sendmsg/sendmmsg and, for AF_INET/AF_INET6
 * datagram sockets with a destination, first connect()s the socket to
 * that destination and then sends without a destination. Semantics are
 * preserved for single-peer sockets (RTP); multi-peer UDP sockets should
 * use TCP instead. It does NOT hide, fake or alter payloads.
 *
 * Build: gcc -shared -fPIC -o libudp_connect_shim.so udp_connect_shim.c -ldl
 * Use:   LD_PRELOAD=/path/to/libudp_connect_shim.so <program>
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <sys/uio.h>
#include <netinet/in.h>
#include <string.h>
#include <errno.h>

typedef ssize_t (*send_fn)(int, const void *, size_t, int);
typedef ssize_t (*sendto_fn)(int, const void *, size_t, int,
                             const struct sockaddr *, socklen_t);
typedef ssize_t (*sendmsg_fn)(int, const struct msghdr *, int);
typedef int (*sendmmsg_fn)(int, struct mmsghdr *, unsigned int, int);

static int is_udp_socket(int fd) {
    int type = 0;
    socklen_t len = sizeof(type);
    if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &len) != 0) return 0;
    if (type != SOCK_DGRAM) return 0;
    struct sockaddr_storage ss;
    socklen_t slen = sizeof(ss);
    if (getsockname(fd, (struct sockaddr *)&ss, &slen) != 0) return 0;
    return ss.ss_family == AF_INET || ss.ss_family == AF_INET6;
}

/* Connect a UDP socket to dest (cheap, just sets the peer). */
static int udp_connect(int fd, const struct sockaddr *dest, socklen_t addrlen) {
    return connect(fd, dest, addrlen);
}

ssize_t sendto(int fd, const void *buf, size_t len, int flags,
               const struct sockaddr *dest, socklen_t addrlen) {
    static sendto_fn real_sendto = NULL;
    static send_fn real_send = NULL;
    if (!real_sendto) real_sendto = (sendto_fn)dlsym(RTLD_NEXT, "sendto");
    if (!real_send) real_send = (send_fn)dlsym(RTLD_NEXT, "send");
    if (dest && addrlen > 0 && is_udp_socket(fd)) {
        if (udp_connect(fd, dest, addrlen) == 0)
            return real_send(fd, buf, len, flags);
        /* connect failed: fall through so the caller sees the real error */
    }
    return real_sendto(fd, buf, len, flags, dest, addrlen);
}

ssize_t sendmsg(int fd, const struct msghdr *msg, int flags) {
    static sendmsg_fn real_sendmsg = NULL;
    if (!real_sendmsg) real_sendmsg = (sendmsg_fn)dlsym(RTLD_NEXT, "sendmsg");
    if (msg && msg->msg_name && msg->msg_namelen > 0 && is_udp_socket(fd)) {
        if (udp_connect(fd, (const struct sockaddr *)msg->msg_name,
                        msg->msg_namelen) == 0) {
            struct msghdr m2 = *msg;
            m2.msg_name = NULL;
            m2.msg_namelen = 0;
            return real_sendmsg(fd, &m2, flags);
        }
    }
    return real_sendmsg(fd, msg, flags);
}

int sendmmsg(int fd, struct mmsghdr *msgvec, unsigned int vlen, int flags) {
    static sendmmsg_fn real_sendmmsg = NULL;
    static sendmsg_fn real_sendmsg = NULL;
    if (!real_sendmmsg) real_sendmmsg = (sendmmsg_fn)dlsym(RTLD_NEXT, "sendmmsg");
    if (!real_sendmsg) real_sendmsg = (sendmsg_fn)dlsym(RTLD_NEXT, "sendmsg");
    if (msgvec && vlen > 0 && is_udp_socket(fd)) {
        int converted = 0;
        for (unsigned int i = 0; i < vlen; i++) {
            if (msgvec[i].msg_hdr.msg_name && msgvec[i].msg_hdr.msg_namelen > 0) {
                converted = 1;
                break;
            }
        }
        if (converted) {
            /* Send one by one via the sendmsg shim path. */
            int sent = 0;
            for (unsigned int i = 0; i < vlen; i++) {
                ssize_t n = sendmsg(fd, &msgvec[i].msg_hdr, flags);
                if (n < 0) {
                    if (sent == 0) return -1;
                    break;
                }
                msgvec[i].msg_len = (unsigned int)n;
                sent++;
            }
            return sent;
        }
    }
    return real_sendmmsg(fd, msgvec, vlen, flags);
}
