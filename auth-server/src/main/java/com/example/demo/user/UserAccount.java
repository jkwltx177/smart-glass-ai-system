package com.example.demo.user;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.NoArgsConstructor;

@Entity
@Table(name = "auth_users")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;

    @Column(name = "company_name", nullable = false, length = 120)
    private String companyName;

    @Column(name = "company_auth_code_hash", nullable = false, length = 255)
    private String companyAuthCodeHash;

    public UserAccount(String username, String passwordHash, String companyName, String companyAuthCodeHash) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.companyName = companyName;
        this.companyAuthCodeHash = companyAuthCodeHash;
    }

    public void changePassword(String encodedPassword) {
        this.passwordHash = encodedPassword;
    }

    public String getUsername() {
        return username;
    }

    public String getPasswordHash() {
        return passwordHash;
    }
}
