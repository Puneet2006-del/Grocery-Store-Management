package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.Dtos.StoreDto;
import com.zerowaste.grocery.dto.ShopDtos.CreateShopRequest;
import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.repository.StoreRepository;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Adding a shop and retrying a failed set-up. The shop's history and forecasts are created by a background job. */
@Service
public class ShopService {

    private static final int MAX_SHOPS = 10;
    private static final Map<String, String> SIZE = Map.of("small", "0.70", "medium", "1.00", "large", "1.30");

    private final JdbcClient jdbc;
    private final AccessService access;
    private final StoreRepository stores;
    private final OnboardingLauncher launcher;

    public ShopService(DataSource dataSource, AccessService access, StoreRepository stores, OnboardingLauncher launcher) {
        this.jdbc = JdbcClient.create(dataSource);
        this.access = access;
        this.stores = stores;
        this.launcher = launcher;
    }

    public StoreDto create(CreateShopRequest req) {
        String name = req.name().trim();
        String city = titleCase(req.city().trim());
        String type = req.type().trim().toLowerCase(Locale.ROOT);
        String size = req.size().trim().toLowerCase(Locale.ROOT);
        if (name.length() < 2 || name.length() > 60) {
            throw new IllegalArgumentException("The shop name must be 2 to 60 characters");
        }
        if (city.length() < 2 || city.length() > 50) {
            throw new IllegalArgumentException("The city must be 2 to 50 characters");
        }
        if (!type.equals("urban") && !type.equals("suburban")) {
            throw new IllegalArgumentException("type must be urban or suburban");
        }
        if (!SIZE.containsKey(size)) {
            throw new IllegalArgumentException("size must be small, medium or large");
        }
        if (req.latitude() < -90 || req.latitude() > 90 || req.longitude() < -180 || req.longitude() > 180) {
            throw new IllegalArgumentException("The location is not a valid latitude and longitude");
        }
        List<String> mine = access.storeIds();
        if (mine.size() >= MAX_SHOPS) {
            throw new IllegalArgumentException("You can have at most " + MAX_SHOPS + " shops");
        }
        long same = jdbc.sql("SELECT COUNT(*) AS c FROM stores WHERE owner_id = :u AND LOWER(name) = :n")
                .param("u", access.userId()).param("n", name.toLowerCase(Locale.ROOT))
                .query((rs, i) -> rs.getLong("c")).list().get(0);
        if (same > 0) {
            throw new IllegalStateException("You already have a shop called " + name);
        }
        long next = jdbc.sql("SELECT COALESCE(MAX(CAST(SUBSTRING(store_id, 2) AS UNSIGNED)), 0) + 1 AS n FROM stores")
                .query((rs, i) -> rs.getLong("n")).list().get(0);
        String id = String.format("S%02d", next);
        jdbc.sql("""
                INSERT INTO stores (store_id, name, city, type, lat, lon, owner_id, status, status_message, size_factor)
                VALUES (:id, :name, :city, :type, :lat, :lon, :owner, 'PENDING', 'Waiting to start', :size)
                """).param("id", id).param("name", name).param("city", city).param("type", type)
                .param("lat", req.latitude()).param("lon", req.longitude()).param("owner", access.userId())
                .param("size", new java.math.BigDecimal(SIZE.get(size))).update();
        startJob(id);
        return stores.findById(id).map(StoreDto::from)
                .orElseThrow(() -> new ResourceNotFoundException("Store not found: " + id));
    }

    public StoreDto retry(String storeId) {
        access.requireStore(storeId);
        String status = jdbc.sql("SELECT status FROM stores WHERE store_id = :id").param("id", storeId)
                .query((rs, i) -> rs.getString("status")).list().get(0);
        if (!"FAILED".equals(status)) {
            throw new IllegalStateException("Only a shop whose set-up failed can be retried");
        }
        jdbc.sql("UPDATE stores SET status = 'PENDING', status_message = 'Retrying' WHERE store_id = :id")
                .param("id", storeId).update();
        startJob(storeId);
        return stores.findById(storeId).map(StoreDto::from)
                .orElseThrow(() -> new ResourceNotFoundException("Store not found: " + storeId));
    }

    private void startJob(String storeId) {
        String result = launcher.start();
        if (!result.equals("started") && !result.equals("already running")) {
            String message = ("Could not start the set-up automatically: " + result
                    + ". Run: python pipeline\\onboard_shops.py").replace("'", "");
            jdbc.sql("UPDATE stores SET status = 'FAILED', status_message = :m WHERE store_id = :id")
                    .param("m", message.length() > 250 ? message.substring(0, 250) : message).param("id", storeId).update();
        }
    }

    private static String titleCase(String s) {
        StringBuilder out = new StringBuilder();
        for (String part : s.toLowerCase(Locale.ROOT).split("\\s+")) {
            if (!part.isEmpty()) {
                out.append(out.length() > 0 ? " " : "").append(Character.toUpperCase(part.charAt(0))).append(part.substring(1));
            }
        }
        return out.toString();
    }
}
