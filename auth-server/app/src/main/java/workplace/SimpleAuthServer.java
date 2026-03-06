/*
#### 다음 실습 코드는 학습 목적으로만 사용 바랍니다. 문의 : audit@korea.ac.kr 임성열 Ph.D.
#### 실습 코드는 완성된 상용 버전이 아니라 교육용으로 제작되었으며, 상용 서비스로 이용하려면 배포 목적에 따라서 보완이 필요합니다.

gradle 디렉토리를 통째로 복사 또는 이동 가이드 (소스를 받았을 때)
이 때, gradlew, settings.gradle(또는 .kts), build.gradle(또는 .kts)가 있는 폴더를 통째로 복사/이동

1. 8080(자바), 8008(FastAPI) 등 사용 포트가 있다면 먼저 끊기
    lsof -iTCP:8080 -sTCP:LISTEN
    lsof -iTCP:8008 -sTCP:LISTEN
2. PID가 있으면 종료
    kill -9 <
3. 새로운 디렉토리 루트에서, Gradle Daemon 종료
    ./gradlew --stop
    또는 pkill -f GradleDaemon || true
4. 프로젝트 로컬 캐시/산출물 완전 삭제
    rm -rf .gradle
    rm -rf build
    find . -name build -type d -prune -exec rm -rf {} +
*/
// 또는 rm -rf **/build
/*
5. 최초 실행 시, 캐시를 끄고 실행
    ./gradlew :app:clean --no-configuration-cache --no-build-cache
    ./gradlew :app:run   --no-configuration-cache --no-build-cache
6. 프로젝트 루트 gradle.properties에 추가:
    org.gradle.configuration-cache=false
    org.gradle.caching=false

7. 인증 서버에 사용할 users 스키마가 생성되어 있어야 함 (Ground Rule : 테이블명은 소문자로 작성)
    CREATE TABLE `users` (
    `id` bigint(20) unsigned NOT NULL AUTO_INCREMENT,
    `username` varchar(100) NOT NULL,
    `password` varchar(255) NOT NULL,
    `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
    `updated_at` timestamp NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_users_username` (`username`)
    ) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    SELECT * FROM sql_db.users;
8. 실행 (예 :루트 디렉토리 workpalce 에서)
    workplace % ./gradlew build
    ./gradlew :app:run --no-configuration-cache 
*/

package workplace;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLIntegrityConstraintViolationException;
import java.sql.Statement;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.Executors;

import org.mindrot.jbcrypt.BCrypt;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

/*
순수 Java + HttpServer + MariaDB + 세션 + JWT 예제

수정 히스토리 내용:
  1) 로그인/회원가입 username/password trim 처리(공백으로 인한 invalid_credentials 방지)
  2) 쿠키 생성/삭제 속성 통일(cookie() 헬퍼)
     - 로그아웃 시 쿠키 삭제 누락/속성 불일치 방지
  3) /api/auth/check CORS + credentials 지원
  4) 로그인 성공 시 http://localhost:8008/index.html 리다이렉트 유지
  5) 로그인 실패 원인 확정용 DEBUG 로그 추가
     - raw params / username/password / bcrypt matches 여부를 콘솔에 출력
 */
public class SimpleAuthServer {

    // ==== DB CONFIG (환경에 맞게 수정) ==== //
    private static final String DB_URL = "jdbc:mariadb://localhost:3379/sql_db";
    private static final String DB_USER = "root";
    private static final String DB_PASSWORD = "SqlDba-1";

    // ==== SESSION STORE ==== //
    private static final Map<String, User> SESSION_STORE = new ConcurrentHashMap<>();
    private static final String SESSION_COOKIE_NAME = "SESSION_ID";

    // ==== JWT COOKIE 이름 ==== //
    private static final String JWT_COOKIE_NAME = "ACCESS_TOKEN";

    // ==== (선택) Vue에서 로그인 여부 판단용 쿠키 이름 ==== //
    private static final String APP_AUTH_COOKIE_NAME = "APP_AUTH";

    // ==== CORS (dev) ==== //
    // 프론트(8008)에서 자바 API(8080) 호출하는 경우 대비
    private static final String DEV_FRONTEND_ORIGIN = "http://localhost:8008";

    // ==== DEBUG ==== //
    private static final boolean DEBUG = true;

    public static void main(String[] args) throws Exception {
        // JDBC 드라이버 로드
        Class.forName("org.mariadb.jdbc.Driver");

        System.out.println("=== SimpleAuthServer v2026-02-03-REPLACED ===");
        System.out.println("Server started at http://localhost:8080");

        UserRepository userRepository = new JdbcUserRepository(DB_URL, DB_USER, DB_PASSWORD);
        AuthService authService = new AuthService(userRepository);

        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);
        server.setExecutor(Executors.newFixedThreadPool(10));

        // GET / -> /login 리다이렉트
        server.createContext("/", exchange -> {
            if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                redirect(exchange, "/login");
            } else {
                methodNotAllowed(exchange);
            }
        });

        // GET /login -> login.html
        server.createContext("/login", exchange -> {
            if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                serveResource(exchange, "web/login.html", "text/html; charset=utf-8");
            } else {
                methodNotAllowed(exchange);
            }
        });

        // GET /signup -> signup.html
        server.createContext("/signup", exchange -> {
            if ("GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                serveResource(exchange, "web/signup.html", "text/html; charset=utf-8");
            } else {
                methodNotAllowed(exchange);
            }
        });

        // GET /static/* -> CSS/JS
        server.createContext("/static", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }
            String path = exchange.getRequestURI().getPath(); // /static/style.css
            String filename = path.replaceFirst("/static/?", "");
            if (filename.isEmpty()) {
                notFound(exchange);
                return;
            }

            String resourcePath = "web/" + filename;
            String contentType;
            if (filename.endsWith(".css")) {
                contentType = "text/css; charset=utf-8";
            } else if (filename.endsWith(".js")) {
                contentType = "application/javascript; charset=utf-8";
            } else {
                contentType = "application/octet-stream";
            }
            serveResource(exchange, resourcePath, contentType);
        });

        // POST /api/signup -> 회원가입
        server.createContext("/api/signup", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }
            Map<String, String> params = parseFormBody(exchange);

            String username = trimToNull(params.get("username"));
            String password = params.get("password");
            if (password != null) password = password.trim();

            if (DEBUG) {
                System.out.println("=== SIGNUP HIT ===");
                System.out.println("[SIGNUP] raw params=" + params);
                System.out.println("[SIGNUP] username=" + username + ", pwLen=" + (password == null ? "null" : password.length()));
            }

            if (isBlank(username) || isBlank(password)) {
                writeText(exchange, 400, "username and password are required");
                return;
            }

            try {
                authService.signUp(username, password);
                redirect(exchange, "/login");
            } catch (SQLIntegrityConstraintViolationException dup) {
                writeText(exchange, 400, "username already exists");
            } catch (Exception e) {
                e.printStackTrace();
                writeText(exchange, 500, "signup error");
            }
        });

        // POST /api/login
        // 로그인 + 세션 + JWT 발급 + (중요) 302 리다이렉트 금지 → 200 JSON 반환
        server.createContext("/api/login", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }

            try {
                Map<String, String> params = parseFormBody(exchange);
                String username = params.get("username");
                String password = params.get("password");

                System.out.println("[LOGIN] content-type=" + exchange.getRequestHeaders().getFirst("Content-Type"));
                System.out.println("[LOGIN] username(trim)=" + (username == null ? "null" : username.trim())
                        + ", pwLen=" + (password == null ? -1 : password.length()));

                if (isBlank(username) || isBlank(password)) {
                    writeJson(exchange, 400, "{\"ok\":false,\"error\":\"username and password are required\"}");
                    return;
                }

                User user = authService.login(username, password);
                if (user == null) {
                    writeJson(exchange, 401, "{\"ok\":false,\"error\":\"invalid credentials\"}");
                    return;
                }

                // 1) 세션 쿠키
                String sessionId = UUID.randomUUID().toString();
                SESSION_STORE.put(sessionId, user);
                exchange.getResponseHeaders().add(
                        "Set-Cookie",
                        SESSION_COOKIE_NAME + "=" + sessionId + "; Path=/; HttpOnly; SameSite=Lax"
                );

                // 2) JWT 쿠키
                String jwt = JwtUtil.createToken(user);
                exchange.getResponseHeaders().add(
                        "Set-Cookie",
                        JWT_COOKIE_NAME + "=" + jwt + "; Path=/; HttpOnly; SameSite=Lax"
                );

                // 3) 프론트에서 로그인 여부 판단용 쿠키 (JS 읽기 가능)
                exchange.getResponseHeaders().add(
                        "Set-Cookie",
                        APP_AUTH_COOKIE_NAME + "=1; Path=/; SameSite=Lax"
                );

                // 4) (가장 중요) 여기서 redirect 하지 말고 200 JSON으로 끝내기
                //    → fetch/XHR 환경에서 302 리다이렉트는 HTTP 0/취소를 유발하기 쉬움
                writeJson(exchange, 200, "{\"ok\":true,\"redirect\":\"http://localhost:8008/index.html\"}");
                System.out.println("[LOGIN] SUCCESS -> 200 JSON (no redirect)");
                return;

            } catch (Exception e) {
                e.printStackTrace();
                // fetch가 HTTP 0이 아니라 500을 받게 JSON으로 응답
                writeJson(exchange, 500, "{\"ok\":false,\"error\":\"login error\"}");
                return;
            }
        });

        // GET /api/auth/check -> 로그인 여부 확인 (세션 또는 JWT)
        server.createContext("/api/auth/check", exchange -> {
            // CORS Preflight
            if ("OPTIONS".equalsIgnoreCase(exchange.getRequestMethod())) {
                addCorsHeaders(exchange);
                exchange.sendResponseHeaders(204, -1);
                exchange.close();
                return;
            }

            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }

            addCorsHeaders(exchange);

            // (A) 세션 검사
            String sessionId = getCookieValue(exchange, SESSION_COOKIE_NAME);
            User sessionUser = null;
            if (!isBlank(sessionId)) {
                sessionUser = SESSION_STORE.get(sessionId);
            }

            // (B) JWT 검사
            String token = getCookieValue(exchange, JWT_COOKIE_NAME);
            boolean jwtOk = false;
            String jwtUsername = null;
            String jwtSubject = null;

            if (!isBlank(token)) {
                try {
                    DecodedJWT decoded = JwtUtil.verifyToken(token);
                    jwtOk = true;
                    jwtUsername = decoded.getClaim("username").asString();
                    jwtSubject = decoded.getSubject();
                } catch (JWTVerificationException ex) {
                    jwtOk = false;
                } catch (Exception ex) {
                    jwtOk = false;
                }
            }

            // 정책: 세션 OR JWT 중 하나라도 유효하면 통과
            if (sessionUser == null && !jwtOk) {
                writeJson(exchange, 401, "{\"ok\":false,\"reason\":\"UNAUTHORIZED\"}");
                return;
            }

            if (sessionUser != null) {
                String body = "{\"ok\":true,\"via\":\"session\",\"username\":\""
                        + escapeJson(sessionUser.getUsername()) + "\"}";
                writeJson(exchange, 200, body);
            } else {
                String body = "{\"ok\":true,\"via\":\"jwt\",\"username\":\""
                        + escapeJson(jwtUsername) + "\",\"sub\":\""
                        + escapeJson(jwtSubject) + "\"}";
                writeJson(exchange, 200, body);
            }
        });

        // (옵션) GET /home -> 8080 내에서 세션 테스트용
        server.createContext("/home", exchange -> {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }
            User user = resolveUser(exchange);
            if (user == null) {
                redirect(exchange, "/login");
                return;
            }
            String body = """
                    <html>
                    <head>
                      <meta charset='utf-8'/>
                      <link rel='stylesheet' href='/static/style.css'/>
                      <title>Home</title>
                    </head>
                    <body>
                      <div class='container'>
                        <h1>Welcome, %s</h1>
                        <p>8080 서버의 /home 페이지입니다.</p>
                        <form method='POST' action='/api/logout'>
                          <button type='submit'>로그아웃</button>
                        </form>
                      </div>
                    </body>
                    </html>
                    """.formatted(escapeHtml(user.getUsername()));
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().add("Content-Type", "text/html; charset=utf-8");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream os = exchange.getResponseBody()) {
                os.write(bytes);
            }
        });

        // POST /api/logout -> 로그아웃
        server.createContext("/api/logout", exchange -> {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                methodNotAllowed(exchange);
                return;
            }

            String sessionId = resolveSessionId(exchange);
            if (sessionId != null) {
                SESSION_STORE.remove(sessionId);
            }

            // 쿠키 제거(동일 속성으로 삭제)
            exchange.getResponseHeaders().add("Set-Cookie", cookie(SESSION_COOKIE_NAME, "", true, 0));
            exchange.getResponseHeaders().add("Set-Cookie", cookie(JWT_COOKIE_NAME, "", true, 0));
            exchange.getResponseHeaders().add("Set-Cookie", cookie(APP_AUTH_COOKIE_NAME, "", false, 0));

            redirect(exchange, "/login");
        });

        server.start();
    }

    // ========= CORS =========

    private static void addCorsHeaders(HttpExchange exchange) {
        exchange.getResponseHeaders().set("Access-Control-Allow-Origin", DEV_FRONTEND_ORIGIN);
        exchange.getResponseHeaders().set("Access-Control-Allow-Credentials", "true");
        exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
        exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
        exchange.getResponseHeaders().set("Vary", "Origin");
    }

    // ========= 리소스/응답 헬퍼 =========

    private static void serveResource(HttpExchange exchange, String resourcePath, String contentType) throws IOException {
        InputStream is = SimpleAuthServer.class.getClassLoader().getResourceAsStream(resourcePath);
        if (is == null) {
            notFound(exchange);
            return;
        }
        byte[] bytes = is.readAllBytes();
        exchange.getResponseHeaders().add("Content-Type", contentType);
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void writeText(HttpExchange exchange, int status, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void writeJson(HttpExchange exchange, int status, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void redirect(HttpExchange exchange, String location) throws IOException {
        exchange.getResponseHeaders().add("Location", location);
        exchange.sendResponseHeaders(302, -1);
        exchange.close();
    }

    private static void methodNotAllowed(HttpExchange exchange) throws IOException {
        writeText(exchange, 405, "Method Not Allowed");
    }

    private static void notFound(HttpExchange exchange) throws IOException {
        writeText(exchange, 404, "Not Found");
    }

    private static Map<String, String> parseFormBody(HttpExchange exchange) throws IOException {
        String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
        Map<String, String> params = new HashMap<>();
        for (String pair : body.split("&")) {
            if (pair.isEmpty()) continue;
            String[] kv = pair.split("=", 2);
            String key = urlDecode(kv[0]);
            String value = kv.length > 1 ? urlDecode(kv[1]) : "";
            params.put(key, value);
        }
        return params;
    }

    private static String urlDecode(String s) {
        return URLDecoder.decode(s, StandardCharsets.UTF_8);
    }

    private static boolean isBlank(String s) {
        return s == null || s.trim().isEmpty();
    }

    private static String trimToNull(String s) {
        if (s == null) return null;
        String t = s.trim();
        return t.isEmpty() ? null : t;
    }

    // ✅ 공통 쿠키 읽기
    private static String getCookieValue(HttpExchange exchange, String name) {
        List<String> cookies = exchange.getRequestHeaders().get("Cookie");
        if (cookies == null) return null;
        for (String header : cookies) {
            String[] parts = header.split(";\\s*");
            for (String part : parts) {
                String[] kv = part.split("=", 2);
                if (kv.length == 2 && name.equals(kv[0])) {
                    return kv[1];
                }
            }
        }
        return null;
    }

    private static String resolveSessionId(HttpExchange exchange) {
        return getCookieValue(exchange, SESSION_COOKIE_NAME);
    }

    private static User resolveUser(HttpExchange exchange) {
        String sessionId = resolveSessionId(exchange);
        if (sessionId == null) return null;
        return SESSION_STORE.get(sessionId);
    }

    private static String escapeHtml(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

    private static String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }

    // ✅ 쿠키 생성 헬퍼(속성 통일)
    // maxAgeSeconds:
    //  -1 : Max-Age 미설정(세션 쿠키처럼 동작)
    //   0 : 즉시 삭제
    private static String cookie(String name, String value, boolean httpOnly, int maxAgeSeconds) {
        StringBuilder sb = new StringBuilder();
        sb.append(name).append("=").append(value == null ? "" : value);
        sb.append("; Path=/");
        if (maxAgeSeconds >= 0) sb.append("; Max-Age=").append(maxAgeSeconds);
        if (httpOnly) sb.append("; HttpOnly");
        sb.append("; SameSite=Lax");
        return sb.toString();
    }

    // ========= 도메인 / 레포지토리 / 서비스 =========

    public static class User {
        private Long id;
        private String username;
        private String password;

        public Long getId() { return id; }
        public void setId(Long id) { this.id = id; }

        public String getUsername() { return username; }
        public void setUsername(String username) { this.username = username; }

        public String getPassword() { return password; }
        public void setPassword(String password) { this.password = password; }
    }

    public interface UserRepository {
        void save(User user) throws Exception;
        User findByUsername(String username) throws Exception;
    }

    public static class JdbcUserRepository implements UserRepository {
        private final String url;
        private final String user;
        private final String password;

        public JdbcUserRepository(String url, String user, String password) {
            this.url = url;
            this.user = user;
            this.password = password;
        }

        private Connection getConnection() throws SQLException {
            return DriverManager.getConnection(url, user, password);
        }

        @Override
        public void save(User u) throws Exception {
            String sql = "INSERT INTO users(username, password) VALUES(?, ?)";
            try (Connection conn = getConnection();
                 PreparedStatement ps = conn.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
                ps.setString(1, u.getUsername());
                ps.setString(2, u.getPassword());
                ps.executeUpdate();
                try (ResultSet rs = ps.getGeneratedKeys()) {
                    if (rs.next()) {
                        u.setId(rs.getLong(1));
                    }
                }
            }
        }

        @Override
        public User findByUsername(String username) throws Exception {
            String sql = "SELECT id, username, password FROM users WHERE username = ?";
            try (Connection conn = getConnection();
                 PreparedStatement ps = conn.prepareStatement(sql)) {
                ps.setString(1, username);
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next()) {
                        User u = new User();
                        u.setId(rs.getLong("id"));
                        u.setUsername(rs.getString("username"));
                        u.setPassword(rs.getString("password"));
                        return u;
                    }
                }
            }
            return null;
        }
    }

    public static class AuthService {
        private final UserRepository userRepository;

        public AuthService(UserRepository userRepository) {
            this.userRepository = userRepository;
        }

        public void signUp(String username, String rawPassword) throws Exception {
            username = trimToNull(username);
            if (rawPassword != null) rawPassword = rawPassword.trim();

            User existing = userRepository.findByUsername(username);
            if (existing != null) {
                throw new SQLIntegrityConstraintViolationException("username already exists");
            }

            String hashed = BCrypt.hashpw(rawPassword, BCrypt.gensalt(12));

            User u = new User();
            u.setUsername(username);
            u.setPassword(hashed);
            userRepository.save(u);
        }

        public User login(String username, String rawPassword) throws Exception {
            username = trimToNull(username);
            if (rawPassword != null) rawPassword = rawPassword.trim();

            User u = userRepository.findByUsername(username);
            if (u == null) {
                if (DEBUG) System.out.println("[AUTH] user not found: " + username);
                return null;
            }
            if (DEBUG) {
                System.out.println("[AUTH] user found: " + username);
                String hash = u.getPassword();
                System.out.println("[AUTH] dbHash prefix: " + (hash == null ? "null" : hash.substring(0, Math.min(7, hash.length()))));
            }

            boolean ok = BCrypt.checkpw(rawPassword, u.getPassword());
            if (DEBUG) System.out.println("[AUTH] bcrypt matches=" + ok);

            if (!ok) return null;
            return u;
        }
    }

    // ========= JWT 유틸 =========

    public static class JwtUtil {
        private static final String SECRET = "RANDOM_SECRET_KEY";
        private static final Algorithm ALG = Algorithm.HMAC256(SECRET);
        private static final String ISSUER = "simple-auth-server";

        public static String createToken(User user) {
            Instant now = Instant.now();
            return JWT.create()
                    .withIssuer(ISSUER)
                    .withIssuedAt(Date.from(now))
                    .withExpiresAt(Date.from(now.plus(1, ChronoUnit.HOURS)))
                    .withSubject(String.valueOf(user.getId()))
                    .withClaim("username", user.getUsername())
                    .sign(ALG);
        }

        public static DecodedJWT verifyToken(String token) throws JWTVerificationException {
            JWTVerifier verifier = JWT.require(ALG)
                    .withIssuer(ISSUER)
                    .build();
            return verifier.verify(token);
        }
    }
}
