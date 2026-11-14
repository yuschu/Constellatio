"""API Key 的落库加密（标准库实现，不新增运行依赖）。

构造：以 `SECRET_KEY` 派生 32 字节主密钥，用 HMAC-SHA256 生成计数器模式的
密钥流做异或，再对 nonce + 密文做 HMAC-SHA256 截断认证（encrypt-then-MAC）。
密文自带版本前缀，旧明文值原样读取，便于从 A 阶段未加密数据平滑过渡。

安全边界：
- 主密钥来自 `SECRET_KEY`，轮换 `SECRET_KEY` 后旧密文无法解密，需要重新填写 API Key。
- 这是应用层字段加密，不是 KMS；拥有数据库与应用密钥的人仍可解密。
"""

import base64
import hashlib
import hmac
import secrets

from django.conf import settings

PREFIX = 'enc:v1:'
_DERIVE_LABEL = b'constellatio.assistant.api-key.derive.v1'
_STREAM_LABEL = b'constellatio.assistant.api-key.stream.v1'
_TAG_LABEL = b'constellatio.assistant.api-key.tag.v1'
_NONCE_BYTES = 16
_TAG_BYTES = 16


def is_encrypted(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def _master_key():
    secret = str(getattr(settings, 'SECRET_KEY', '') or '').encode('utf-8')
    # SECRET_KEY 本身是高熵密钥，用 HMAC 做域分离即可，不需要 PBKDF2。
    return hmac.new(secret, _DERIVE_LABEL, hashlib.sha256).digest()


def _keystream(master_key, nonce, length):
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(
            master_key,
            _STREAM_LABEL + nonce + counter.to_bytes(8, 'big'),
            hashlib.sha256,
        ).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def _tag(master_key, nonce, ciphertext):
    return hmac.new(
        master_key, _TAG_LABEL + nonce + ciphertext, hashlib.sha256
    ).digest()[:_TAG_BYTES]


def _b64encode(value):
    return base64.urlsafe_b64encode(value).decode('ascii')


def _b64decode(value):
    return base64.urlsafe_b64decode(value.encode('ascii'))


def encrypt_secret(value):
    """空值返回空串；已加密值原样返回；其余按 v1 格式加密。"""
    if not value:
        return ''
    if is_encrypted(value):
        return value
    plaintext = str(value).encode('utf-8')
    nonce = secrets.token_bytes(_NONCE_BYTES)
    master_key = _master_key()
    stream = _keystream(master_key, nonce, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, stream, strict=True))
    tag = _tag(master_key, nonce, ciphertext)
    return PREFIX + '.'.join((
        _b64encode(nonce), _b64encode(ciphertext), _b64encode(tag)))


def decrypt_secret(value):
    """解密 v1 密文；旧明文原样返回；密文损坏或密钥不匹配返回空串。"""
    if not value:
        return ''
    if not is_encrypted(value):
        return value
    try:
        nonce_b64, ciphertext_b64, tag_b64 = value[len(PREFIX):].split('.', 2)
        nonce = _b64decode(nonce_b64)
        ciphertext = _b64decode(ciphertext_b64)
        tag = _b64decode(tag_b64)
    except (ValueError, TypeError):
        return ''
    if len(nonce) != _NONCE_BYTES or len(tag) != _TAG_BYTES:
        return ''
    master_key = _master_key()
    if not hmac.compare_digest(tag, _tag(master_key, nonce, ciphertext)):
        return ''
    stream = _keystream(master_key, nonce, len(ciphertext))
    plaintext = bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))
    try:
        return plaintext.decode('utf-8')
    except UnicodeDecodeError:
        return ''
