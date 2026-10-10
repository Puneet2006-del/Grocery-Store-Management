package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.PlannerDtos.RuleDto;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import java.sql.Timestamp;
import java.util.List;
import java.util.Optional;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Reads and edits the configurable business rules used by the agents. */
@Service
public class RuleService {

    private final JdbcClient jdbc;

    public RuleService(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    private static RuleDto map(java.sql.ResultSet rs) throws java.sql.SQLException {
        Timestamp t = rs.getTimestamp("updated_at");
        return new RuleDto(rs.getString("rule_key"), rs.getString("rule_value"),
                rs.getString("description"), t == null ? null : t.toLocalDateTime());
    }

    public List<RuleDto> all() {
        return jdbc.sql("SELECT rule_key, rule_value, description, updated_at FROM business_rules ORDER BY rule_key")
                .query((rs, i) -> map(rs)).list();
    }

    /** Numeric value of a rule, or the fallback when it is missing. */
    public double number(String key, double fallback) {
        List<String> v = jdbc.sql("SELECT rule_value FROM business_rules WHERE rule_key = :k")
                .param("k", key).query((rs, i) -> rs.getString("rule_value")).list();
        if (v.isEmpty()) {
            return fallback;
        }
        try {
            return Double.parseDouble(v.get(0).trim());
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    public RuleDto update(String key, String value) {
        Optional<RuleDto> existing = jdbc.sql(
                        "SELECT rule_key, rule_value, description, updated_at FROM business_rules WHERE rule_key = :k")
                .param("k", key).query((rs, i) -> map(rs)).list().stream().findFirst();
        if (existing.isEmpty()) {
            throw new ResourceNotFoundException("Rule not found: " + key);
        }
        String v = value.trim();
        switch (key) {
            case "require_planner_approval" -> {
                if (!v.equalsIgnoreCase("true") && !v.equalsIgnoreCase("false")) {
                    throw new IllegalArgumentException(key + " must be true or false");
                }
                v = v.toLowerCase();
            }
            case "markdown_steps" -> {
                for (String part : v.split(",")) {
                    double d = parse(key, part.trim());
                    if (d <= 0 || d > 100) {
                        throw new IllegalArgumentException("markdown_steps values must be between 0 and 100");
                    }
                }
            }
            default -> {
                double d = parse(key, v);
                if (d < 0) {
                    throw new IllegalArgumentException(key + " must not be negative");
                }
                if ((key.equals("service_level_target") || key.equals("min_confidence")) && d > 1) {
                    throw new IllegalArgumentException(key + " must be between 0 and 1");
                }
                if (key.equals("max_markdown_pct") && d > 100) {
                    throw new IllegalArgumentException("max_markdown_pct must be at most 100");
                }
            }
        }
        jdbc.sql("UPDATE business_rules SET rule_value = :v WHERE rule_key = :k")
                .param("v", v).param("k", key).update();
        return jdbc.sql("SELECT rule_key, rule_value, description, updated_at FROM business_rules WHERE rule_key = :k")
                .param("k", key).query((rs, i) -> map(rs)).list().get(0);
    }

    private static double parse(String key, String s) {
        try {
            return Double.parseDouble(s);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(key + " must be a number");
        }
    }
}
