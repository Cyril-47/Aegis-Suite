import sys
import base64

class DPAPIEncryption:
    """Windows Data Protection API (DPAPI) wrapper with cross-platform fallback."""
    _PREFIX = "dpapi:"

    @classmethod
    def is_available(cls) -> bool:
        return sys.platform == "win32"

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        if not plaintext:
            return ""
        if not cls.is_available():
            return plaintext

        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        data_bytes = plaintext.encode("utf-8")
        blob_in = DATA_BLOB(len(data_bytes), ctypes.cast(ctypes.create_string_buffer(data_bytes), ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()

        success = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(blob_in), wintypes.LPCWSTR("Aegis Bot Token"), None, None, None, 0x01, ctypes.byref(blob_out)
        )
        if not success:
            raise OSError("DPAPI encryption failed.")

        try:
            encrypted_data = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            b64_data = base64.b64encode(encrypted_data).decode("utf-8")
            return f"{cls._PREFIX}{b64_data}"
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if not ciphertext.startswith(cls._PREFIX):
            return ciphertext
        if not cls.is_available():
            raise OSError("Attempted to decrypt DPAPI data on a non-Windows environment.")

        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        b64_bytes = ciphertext[len(cls._PREFIX):].encode("utf-8")
        encrypted_bytes = base64.b64decode(b64_bytes)
        blob_in = DATA_BLOB(len(encrypted_bytes), ctypes.cast(ctypes.create_string_buffer(encrypted_bytes), ctypes.POINTER(ctypes.c_byte)))
        blob_out = DATA_BLOB()

        success = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)
        )
        if not success:
            raise OSError("DPAPI decryption failed.")

        try:
            decrypted_bytes = ctypes.string_at(blob_out.pbData, blob_out.cbData)
            return decrypted_bytes.decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
