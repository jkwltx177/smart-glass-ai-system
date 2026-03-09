package com.example.demo.auth;

import com.example.demo.auth.dto.LoginRequest;
import com.example.demo.auth.dto.LoginResponse;
import com.example.demo.auth.dto.RegisterRequest;
import com.example.demo.user.UserAccount;
import com.example.demo.user.UserRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Transactional(readOnly = true)
public class AuthService {

    private final UserRepository userRepository;
    private final JwtTokenProvider jwtTokenProvider;
    private final JdbcTemplate jdbcTemplate;
    private final PasswordEncoder passwordEncoder = new BCryptPasswordEncoder();
    private final String signupVerificationCode;

    public AuthService(
            UserRepository userRepository,
            JwtTokenProvider jwtTokenProvider,
            JdbcTemplate jdbcTemplate,
            @Value("${auth.signup-verification-code}") String signupVerificationCode
    ) {
        this.userRepository = userRepository;
        this.jwtTokenProvider = jwtTokenProvider;
        this.jdbcTemplate = jdbcTemplate;
        this.signupVerificationCode = signupVerificationCode;
    }

    @Transactional
    public void register(RegisterRequest request) {
        validateRegisterRequest(request);
        if (userRepository.existsByUsername(request.username())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 존재하는 사용자명입니다.");
        }
        String encodedPassword = passwordEncoder.encode(request.password());
        String encodedCompanyCode = passwordEncoder.encode(request.companyAuthCode());
        userRepository.save(
                new UserAccount(
                        request.username(),
                        encodedPassword,
                        request.companyName(),
                        encodedCompanyCode
                )
        );
        upsertProjectUser(request.username(), encodedPassword);
    }

    @Transactional
    public LoginResponse login(LoginRequest request) {
        validateCredentials(request.username(), request.password());
        UserAccount user = userRepository.findByUsername(request.username())
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다."));

        if (!isValidPassword(request.password(), user)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다.");
        }

        String role = resolveProjectRole(user.getUsername());
        String token = jwtTokenProvider.createToken(user.getUsername(), role);
        return new LoginResponse(token, "Bearer", jwtTokenProvider.getExpiresInSeconds());
    }

    private void validateCredentials(String username, String password) {
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "username, password는 필수입니다.");
        }
    }

    private void validateRegisterRequest(RegisterRequest request) {
        validateCredentials(request.username(), request.password());
        if (request.companyName() == null || request.companyName().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "companyName은 필수입니다.");
        }
        if (request.companyAuthCode() == null || request.companyAuthCode().isBlank()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "companyAuthCode는 필수입니다.");
        }
        if (!request.companyAuthCode().equals(signupVerificationCode)) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "회사 인증 코드가 올바르지 않습니다.");
        }
    }

    private boolean isValidPassword(String rawPassword, UserAccount user) {
        String savedPassword = user.getPasswordHash();
        if (savedPassword != null && savedPassword.startsWith("$2")) {
            return passwordEncoder.matches(rawPassword, savedPassword);
        }
        if (rawPassword.equals(savedPassword)) {
            user.changePassword(passwordEncoder.encode(rawPassword));
            return true;
        }
        return false;
    }

    private void upsertProjectUser(String username, String encodedPassword) {
        jdbcTemplate.update(
                """
                INSERT INTO users (username, password_hash, role, is_active, created_at, updated_at)
                VALUES (?, ?, 'FIELD_OPERATOR', TRUE, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    password_hash = VALUES(password_hash),
                    is_active = TRUE,
                    updated_at = NOW()
                """,
                username,
                encodedPassword
        );
    }

    private String resolveProjectRole(String username) {
        try {
            String role = jdbcTemplate.queryForObject(
                    "SELECT role FROM users WHERE username = ? LIMIT 1",
                    String.class,
                    username
            );
            if (role == null || role.isBlank()) {
                return "FIELD_OPERATOR";
            }
            return role;
        } catch (Exception ignored) {
            return "FIELD_OPERATOR";
        }
    }
}
