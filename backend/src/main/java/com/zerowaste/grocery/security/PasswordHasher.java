package com.zerowaste.grocery.security;

import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

/** Salted PBKDF2-HMAC-SHA256 password hashing (120,000 rounds). The same scheme is used by the Python seed script. */
public final class PasswordHasher {

    private static final int ROUNDS = 120_000;
    private static final int KEY_BITS = 256;

    private PasswordHasher() {
    }

    public static String newSalt() {
        byte[] salt = new byte[16];
        new SecureRandom().nextBytes(salt);
        return Base64.getEncoder().encodeToString(salt);
    }

    public static String hash(String password, String saltBase64) {
        try {
            PBEKeySpec spec = new PBEKeySpec(password.toCharArray(), Base64.getDecoder().decode(saltBase64), ROUNDS, KEY_BITS);
            byte[] key = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();
            return Base64.getEncoder().encodeToString(key);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Password hashing is not available", e);
        }
    }

    public static boolean verify(String password, String saltBase64, String expectedHash) {
        return MessageDigest.isEqual(hash(password, saltBase64).getBytes(), expectedHash.getBytes());
    }
}
