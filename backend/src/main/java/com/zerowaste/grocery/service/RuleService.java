package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.AuthDtos.UserDto;
import com.zerowaste.grocery.dto.PlannerDtos.RuleDto;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.security.UserContext;
import java.sql.Timestamp;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/**
 * Business rules. business_rules holds the defaults; each shopkeeper can override any rule for their own
 * business (owner_rules). One shopkeeper's change never affects another's.
 */
@Service
public class RuleService {

    private static final String EFFECTIVE = """
            SELECT b.rule_key, COALESCE(o.rule_value, b.rule_value) AS rule_value, b.description,
                   COALESCE(o.updated_at, b.updated_at) AS updated_at,
                   CASE WHEN o.rule_key IS NULL THEN 0 ELSE 1 END AS customised
            FROM business_rules b
            LEFT JOIN owner_rules o ON o.rule_key = b.rule_key AND o.owner_id = :u
            """;

    private final JdbcClient jdbc;

    public RuleService(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    private static RuleDto map(java.sql.ResultSet rs) throws java.sql.SQLException {
        Timestamp t = rs.getTimestamp("updated_at");
        return new RuleDto(rs.getString("rule_key"), rs.getString("rule_value"), rs.getString("description"),
                t == null ? null : t.toLocalDateTime(), rs.getInt("customised") == 1);
    }

    private static long owner() {
        return UserContext.require().userId();
    }

    /** The rules that apply to the signed-in shopkeeper. */
    public List<RuleDto> all() {
        return jdbc.sql(EFFECTIVE + " ORDER BY b.rule_key").param("u", owner()).query((rs, i) -> map(rs)).list();
    }

    /** Numeric value of a rule for the signed-in shopkeeper, or the fallback when missing. */
    public double number(String key, double fallback) {
        UserDto user = UserContext.get();
        long u = user == null ? -1 : user.userId();
        List<String> v = jdbc.sql(EFFECTIVE + " WHERE b.rule_key = :k").param("u", u).param("k", key)
                .query((rs, i) -> rs.getString("rule_value")).list();
        if (v.isEmpty()) {
            return fallback;
        }
        try {
            return Double.parseDouble(v.get(0).trim());
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private RuleDto one(String key) {
        return jdbc.sql(EFFECTIVE + " WHERE b.rule_key = :k").param("u", owner()).param("k", key)
                .query((rs, i) -> map(rs)).list().stream().findFirst()
                .orElseThrow(() -> new ResourceNotFoundException("Rule not found: " + key));
    }

    public RuleDto update(String key, String value) {
        one(key);                                       // 404 if the rule does not exist
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
        jdbc.sql("DELETE FROM owner_rules WHERE owner_id = :u AND rule_key = :k").param("u", owner()).param("k", key).update();
        jdbc.sql("INSERT INTO owner_rules (owner_id, rule_key, rule_value) VALUES (:u, :k, :v)")
                .param("u", owner()).param("k", key).param("v", v).update();
        return one(key);
    }

    /** Go back to the default value. */
    public RuleDto reset(String key) {
        one(key);
        jdbc.sql("DELETE FROM owner_rules WHERE owner_id = :u AND rule_key = :k").param("u", owner()).param("k", key).update();
        return one(key);
    }

    private static double parse(String key, String s) {
        try {
            return Double.parseDouble(s);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(key + " must be a number");
        }
    }
}
