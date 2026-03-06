package com.example.demo.user;

import jakarta.persistence.*;
import lombok.*;

@Getter
@Entity
@Table(name = "users")
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class UserAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 50)
    private String username;

    @Column(nullable = false)
    private String password;

    public UserAccount(String username, String password) {
        this.username = username;
        this.password = password;
    }

    public void changePassword(String encodedPassword) {
        this.password = encodedPassword;
    }
}
