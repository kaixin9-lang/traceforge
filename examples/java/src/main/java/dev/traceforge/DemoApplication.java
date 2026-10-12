package dev.traceforge;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.Map;

@SpringBootApplication
@RestController
public class DemoApplication {
    private final JdbcTemplate jdbc;
    public DemoApplication(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    public static void main(String[] args) { SpringApplication.run(DemoApplication.class, args); }
    @GetMapping("/health") public Map<String,Object> health() {
        return Map.of("ok",true,"database",jdbc.queryForObject("SELECT 1",Integer.class));
    }
}
