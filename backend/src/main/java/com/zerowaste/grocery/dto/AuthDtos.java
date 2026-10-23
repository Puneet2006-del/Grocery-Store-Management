package com.zerowaste.grocery.dto;

import jakarta.validation.constraints.NotBlank;
import java.util.List;

/** Request and response shapes for accounts and sign-in. */
public final class AuthDtos {

    private AuthDtos() {
    }

    public record UserDto(long userId, String email, String displayName) {
    }

    public record RegisterRequest(@NotBlank(message = "email is required") String email,
                                  @NotBlank(message = "password is required") String password,
                                  @NotBlank(message = "name is required") String displayName) {
    }

    public record LoginRequest(@NotBlank(message = "email is required") String email,
                               @NotBlank(message = "password is required") String password) {
    }

    /** The token is sent back on every request as "Authorization: Bearer <token>". */
    public record AuthResponse(String token, UserDto user) {
    }

    public record MeResponse(UserDto user, List<String> storeIds) {
    }
}
