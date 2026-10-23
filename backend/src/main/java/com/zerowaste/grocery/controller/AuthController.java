package com.zerowaste.grocery.controller;

import com.zerowaste.grocery.dto.AuthDtos.AuthResponse;
import com.zerowaste.grocery.dto.AuthDtos.LoginRequest;
import com.zerowaste.grocery.dto.AuthDtos.MeResponse;
import com.zerowaste.grocery.dto.AuthDtos.RegisterRequest;
import com.zerowaste.grocery.security.UserContext;
import com.zerowaste.grocery.service.AccessService;
import com.zerowaste.grocery.service.AuthService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Create an account, sign in, sign out, and ask who is signed in. */
@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService auth;
    private final AccessService access;

    public AuthController(AuthService auth, AccessService access) {
        this.auth = auth;
        this.access = access;
    }

    @PostMapping("/register")
    public AuthResponse register(@Valid @RequestBody RegisterRequest request) {
        return auth.register(request.email(), request.password(), request.displayName());
    }

    @PostMapping("/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest request) {
        return auth.login(request.email(), request.password());
    }

    @PostMapping("/logout")
    public Map<String, Object> logout(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ")) {
            auth.logout(header.substring(7).trim());
        }
        return Map.of("signedOut", true);
    }

    @GetMapping("/me")
    public MeResponse me() {
        return new MeResponse(UserContext.require(), access.storeIds());
    }
}
