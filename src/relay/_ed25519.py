# ed25519.py - Optimized version of the reference implementation of Ed25519
#
# Written in 2011? by Daniel J. Bernstein <djb@cr.yp.to>
# 2013 by Donald Stufft <donald@stufft.io>
# 2013 by Alex Gaynor <alex.gaynor@gmail.com>
# 2013 by Greg Price <price@mit.edu>
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty.
#
# Source: https://github.com/pyca/ed25519 (CC0)
#
# IMPORTANT: Only safe for verifying public signatures on public messages
# (Discord interaction verification). Do not use for secret-key operations.

"""Pure-Python Ed25519 signature verification (public messages only)."""

from __future__ import annotations

import hashlib

b = 256
q = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493  # curve order


def H(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def pow2(x: int, p: int) -> int:
    while p > 0:
        x = x * x % q
        p -= 1
    return x


def inv(z: int) -> int:
    z2 = z * z % q
    z9 = pow2(z2, 2) * z % q
    z11 = z9 * z2 % q
    z2_5_0 = (z11 * z11) % q * z9 % q
    z2_10_0 = pow2(z2_5_0, 5) * z2_5_0 % q
    z2_20_0 = pow2(z2_10_0, 10) * z2_10_0 % q
    z2_40_0 = pow2(z2_20_0, 20) * z2_20_0 % q
    z2_50_0 = pow2(z2_40_0, 10) * z2_10_0 % q
    z2_100_0 = pow2(z2_50_0, 50) * z2_50_0 % q
    z2_200_0 = pow2(z2_100_0, 100) * z2_100_0 % q
    z2_250_0 = pow2(z2_200_0, 50) * z2_50_0 % q
    return pow2(z2_250_0, 5) * z11 % q


d = -121665 * inv(121666) % q
SQRT_M1 = pow(2, (q - 1) // 4, q)


def xrecover(y: int) -> int:
    xx = (y * y - 1) * inv(d * y * y + 1)
    x = pow(xx, (q + 3) // 8, q)
    if (x * x - xx) % q != 0:
        x = (x * SQRT_M1) % q
    if x % 2 != 0:
        x = q - x
    return x


By = 4 * inv(5)
Bx = xrecover(By)
B = (Bx % q, By % q, 1, (Bx * By) % q)
ident = (0, 1, 1, 0)


def edwards_add(P, Q):  # type: ignore[no-untyped-def]
    (x1, y1, z1, t1) = P
    (x2, y2, z2, t2) = Q
    a = (y1 - x1) * (y2 - x2) % q
    b_ = (y1 + x1) * (y2 + x2) % q
    c = t1 * 2 * d * t2 % q
    dd = z1 * 2 * z2 % q
    e = b_ - a
    f = dd - c
    g = dd + c
    h = b_ + a
    return (e * f % q, g * h % q, f * g % q, e * h % q)


def edwards_double(P):  # type: ignore[no-untyped-def]
    (x1, y1, z1, _t1) = P
    a = x1 * x1 % q
    b_ = y1 * y1 % q
    c = 2 * z1 * z1 % q
    e = ((x1 + y1) * (x1 + y1) - a - b_) % q
    g = -a + b_
    f = g - c
    h = -a - b_
    return (e * f % q, g * h % q, f * g % q, e * h % q)


def scalarmult(P, e):  # type: ignore[no-untyped-def]
    if e == 0:
        return ident
    Q = scalarmult(P, e // 2)
    Q = edwards_double(Q)
    if e & 1:
        Q = edwards_add(Q, P)
    return Q


Bpow: list[tuple[int, int, int, int]] = []


def make_Bpow() -> None:
    P = B
    for _i in range(253):
        Bpow.append(P)
        P = edwards_double(P)


make_Bpow()


def scalarmult_B(e: int):  # type: ignore[no-untyped-def]
    e = e % L
    P = ident
    for i in range(253):
        if e & 1:
            P = edwards_add(P, Bpow[i])
        e = e // 2
    assert e == 0, e
    return P


def encodeint(y: int) -> bytes:
    bits = [(y >> i) & 1 for i in range(b)]
    return bytes(
        [sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(b // 8)]
    )


def encodepoint(P):  # type: ignore[no-untyped-def]
    (x, y, z, _t) = P
    zi = inv(z)
    x = (x * zi) % q
    y = (y * zi) % q
    bits = [(y >> i) & 1 for i in range(b - 1)] + [x & 1]
    return bytes(
        [sum([bits[i * 8 + j] << j for j in range(8)]) for i in range(b // 8)]
    )


def bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def Hint(m: bytes) -> int:
    h = H(m)
    return sum(2**i * bit(h, i) for i in range(2 * b))


def isoncurve(P) -> bool:  # type: ignore[no-untyped-def]
    (x, y, z, t) = P
    return (
        z % q != 0
        and x * y % q == z * t % q
        and (y * y - x * x - z * z - d * t * t) % q == 0
    )


def decodeint(s: bytes) -> int:
    return sum(2**i * bit(s, i) for i in range(0, b))


def decodepoint(s: bytes):  # type: ignore[no-untyped-def]
    y = sum(2**i * bit(s, i) for i in range(0, b - 1))
    x = xrecover(y)
    if x & 1 != bit(s, b - 1):
        x = q - x
    P = (x, y, 1, (x * y) % q)
    if not isoncurve(P):
        raise ValueError("decoding point that is not on curve")
    return P


class SignatureMismatch(Exception):
    pass


def checkvalid(s: bytes, m: bytes, pk: bytes) -> None:
    """Verify Ed25519 signature ``s`` over message ``m`` with public key ``pk``.

    Safe only for public messages / public keys (e.g. Discord interactions).
    """
    if len(s) != b // 4:
        raise ValueError("signature length is wrong")
    if len(pk) != b // 8:
        raise ValueError("public-key length is wrong")

    R = decodepoint(s[: b // 8])
    A = decodepoint(pk)
    S = decodeint(s[b // 8 : b // 4])
    h = Hint(encodepoint(R) + pk + m)

    P = scalarmult_B(S)
    Q = edwards_add(R, scalarmult(A, h))
    (x1, y1, z1, _t1) = P
    (x2, y2, z2, _t2) = Q

    if (
        not isoncurve(P)
        or not isoncurve(Q)
        or (x1 * z2 - x2 * z1) % q != 0
        or (y1 * z2 - y2 * z1) % q != 0
    ):
        raise SignatureMismatch("signature does not pass verification")


def publickey_unsafe(sk: bytes) -> bytes:
    """Testing only — not side-channel safe."""
    h = H(sk)
    a = 2 ** (b - 2) + sum(2**i * bit(h, i) for i in range(3, b - 2))
    return encodepoint(scalarmult_B(a))


def signature_unsafe(m: bytes, sk: bytes, pk: bytes) -> bytes:
    """Testing only — not side-channel safe."""
    h = H(sk)
    a = 2 ** (b - 2) + sum(2**i * bit(h, i) for i in range(3, b - 2))
    r = Hint(bytes([h[j] for j in range(b // 8, b // 4)]) + m)
    R = scalarmult_B(r)
    S = (r + Hint(encodepoint(R) + pk + m) * a) % L
    return encodepoint(R) + encodeint(S)
