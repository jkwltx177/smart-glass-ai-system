package com.example.demo.auth.dto;
public record RegisterRequest(
        String username,
        String password,
        String companyName,
        String companyAuthCode
) {}
