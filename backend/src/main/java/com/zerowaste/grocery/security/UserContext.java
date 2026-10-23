package com.zerowaste.grocery.security;

import com.zerowaste.grocery.dto.AuthDtos.UserDto;
import com.zerowaste.grocery.exception.UnauthorizedException;

/** The signed-in user for the request being handled (one request runs on one thread). */
public final class UserContext {

    private static final ThreadLocal<UserDto> CURRENT = new ThreadLocal<>();

    private UserContext() {
    }

    public static void set(UserDto user) {
        CURRENT.set(user);
    }

    public static UserDto get() {
        return CURRENT.get();
    }

    public static UserDto require() {
        UserDto u = CURRENT.get();
        if (u == null) {
            throw new UnauthorizedException("Sign in required");
        }
        return u;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
