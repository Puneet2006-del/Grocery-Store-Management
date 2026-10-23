package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.AuthDtos.AuthResponse;
import com.zerowaste.grocery.dto.AuthDtos.UserDto;
import com.zerowaste.grocery.exception.UnauthorizedException;
import com.zerowaste.grocery.security.PasswordHasher;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import java.util.List;
import java.util.Optional;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Registration, sign-in and sign-out. Passwords are salted and hashed; tokens are stored only as hashes. */
@Service
public class AuthService {

    private static final int TOKEN_DAYS = 7;
    private final JdbcClient jdbc;

    public AuthService(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    public AuthResponse register(String email, String password, String displayName) {
        String mail = email.trim().toLowerCase();
        if (!mail.matches("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")) {
            throw new IllegalArgumentException("Enter a valid email address");
        }
        if (password.length() < 8) {
            throw new IllegalArgumentException("The password must be at least 8 characters");
        }
        if (displayName.trim().length() < 2) {
            throw new IllegalArgumentException("Enter your name or your business name");
        }
        List<Long> existing = jdbc.sql("SELECT user_id FROM users WHERE email = :e").param("e", mail)
                .query((rs, i) -> rs.getLong("user_id")).list();
        if (!existing.isEmpty()) {
            throw new IllegalStateException("An account with this email already exists");
        }
        String salt = PasswordHasher.newSalt();
        jdbc.sql("INSERT INTO users (email, display_name, password_salt, password_hash) VALUES (:e, :n, :s, :h)")
                .param("e", mail).param("n", displayName.trim()).param("s", salt)
                .param("h", PasswordHasher.hash(password, salt)).update();
        return login(mail, password);
    }

    public AuthResponse login(String email, String password) {
        String mail = email.trim().toLowerCase();
        List<String[]> rows = jdbc.sql("SELECT user_id, display_name, password_salt, password_hash FROM users WHERE email = :e")
                .param("e", mail).query((rs, i) -> new String[]{String.valueOf(rs.getLong("user_id")),
                        rs.getString("display_name"), rs.getString("password_salt"), rs.getString("password_hash")}).list();
        // the same message for an unknown email and a wrong password, so accounts cannot be probed
        if (rows.isEmpty() || !PasswordHasher.verify(password, rows.get(0)[2], rows.get(0)[3])) {
            throw new UnauthorizedException("Invalid email or password");
        }
        long userId = Long.parseLong(rows.get(0)[0]);
        byte[] raw = new byte[32];
        new SecureRandom().nextBytes(raw);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(raw);
        jdbc.sql("INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (:h, :u, :x)")
                .param("h", sha256(token)).param("u", userId).param("x", LocalDateTime.now().plusDays(TOKEN_DAYS)).update();
        return new AuthResponse(token, new UserDto(userId, mail, rows.get(0)[1]));
    }

    public Optional<UserDto> userForToken(String token) {
        return jdbc.sql("""
                SELECT u.user_id, u.email, u.display_name FROM auth_tokens t
                JOIN users u ON u.user_id = t.user_id
                WHERE t.token_hash = :h AND t.expires_at > :now
                """).param("h", sha256(token)).param("now", LocalDateTime.now())
                .query((rs, i) -> new UserDto(rs.getLong("user_id"), rs.getString("email"), rs.getString("display_name")))
                .list().stream().findFirst();
    }

    public void logout(String token) {
        jdbc.sql("DELETE FROM auth_tokens WHERE token_hash = :h").param("h", sha256(token)).update();
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
