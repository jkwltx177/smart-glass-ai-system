package com.example.demo.auth.dto;
public record LoginResponse(String accessToken, String tokenType, long expiresInSeconds) {}
