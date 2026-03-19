# 1. 빌드 단계 (Java 21을 지원하는 Gradle 환경)
FROM gradle:8.5-jdk21 AS builder
WORKDIR /app
COPY . .
# 실행 권한 부여 및 jar 파일 빌드 (테스트 생략으로 속도 향상)
RUN chmod +x gradlew
RUN ./gradlew clean bootJar -x test

# 2. 실행 단계 (가볍고 안전한 Java 21 실행 환경)
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=builder /app/build/libs/*.jar app.jar
ENTRYPOINT ["java", "-jar", "app.jar"]