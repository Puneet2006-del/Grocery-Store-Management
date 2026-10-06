package com.zerowaste.grocery.service;

import com.zerowaste.grocery.dto.Dtos.BatchItem;
import com.zerowaste.grocery.dto.Dtos.InventorySummaryItem;
import com.zerowaste.grocery.entity.Batch;
import com.zerowaste.grocery.entity.Product;
import com.zerowaste.grocery.entity.Store;
import com.zerowaste.grocery.repository.BatchRepository;
import com.zerowaste.grocery.repository.ProductRepository;
import com.zerowaste.grocery.repository.StoreRepository;
import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final BatchRepository batchRepository;
    private final StoreRepository storeRepository;
    private final ProductRepository productRepository;
    private final LocalDate defaultAsOf;

    /**
     * The simulated data ends on a fixed date, so "today" for expiry maths is
     * app.as-of-date (set in application.properties), not the real clock.
     */
    public InventoryService(BatchRepository batchRepository,
                            StoreRepository storeRepository,
                            ProductRepository productRepository,
                            @Value("${app.as-of-date}") String asOfDate) {
        this.batchRepository = batchRepository;
        this.storeRepository = storeRepository;
        this.productRepository = productRepository;
        this.defaultAsOf = LocalDate.parse(asOfDate);
    }

    public LocalDate defaultAsOf() {
        return defaultAsOf;
    }

    public static String freshness(long daysToExpiry) {
        if (daysToExpiry <= 0) {
            return "EXPIRED";
        }
        if (daysToExpiry <= 1) {
            return "CRITICAL";
        }
        if (daysToExpiry <= 3) {
            return "WARNING";
        }
        return "OK";
    }

    /** Batch-level view: every batch with stock left, with days to expiry. */
    public List<BatchItem> batchItems(String storeId, String skuId, String category, LocalDate asOf) {
        LocalDate ref = asOf != null ? asOf : defaultAsOf;
        Map<String, Store> stores = storeRepository.findAll().stream()
                .collect(Collectors.toMap(Store::getStoreId, Function.identity()));
        Map<String, Product> products = productRepository.findAll().stream()
                .collect(Collectors.toMap(Product::getSkuId, Function.identity()));

        List<BatchItem> out = new ArrayList<>();
        for (Batch b : batchRepository.findByQtyRemainingGreaterThanOrderByExpiryDateAsc(0)) {
            Store s = stores.get(b.getStoreId());
            Product p = products.get(b.getSkuId());
            if (s == null || p == null) {
                continue;
            }
            if (storeId != null && !storeId.equals(b.getStoreId())) {
                continue;
            }
            if (skuId != null && !skuId.equals(b.getSkuId())) {
                continue;
            }
            if (category != null && !category.equalsIgnoreCase(p.getCategory())) {
                continue;
            }
            long days = ChronoUnit.DAYS.between(ref, b.getExpiryDate());
            out.add(new BatchItem(b.getBatchId(), b.getStoreId(), s.getName(), b.getSkuId(),
                    p.getName(), p.getCategory(), p.getUnit(), b.getReceivedDate(), b.getExpiryDate(),
                    b.getQtyReceived(), b.getQtyRemaining(), days, freshness(days)));
        }
        return out;
    }

    /** One row per store and SKU, including SKUs with zero stock (stockouts). */
    public List<InventorySummaryItem> summary(String storeId, String category, LocalDate asOf) {
        LocalDate ref = asOf != null ? asOf : defaultAsOf;
        Map<String, List<BatchItem>> grouped = batchItems(storeId, null, category, ref).stream()
                .collect(Collectors.groupingBy(i -> i.storeId() + "|" + i.skuId()));
        List<Product> products = productRepository.findAllByOrderBySkuIdAsc();

        List<InventorySummaryItem> rows = new ArrayList<>();
        for (Store s : storeRepository.findAll(Sort.by("storeId"))) {
            if (storeId != null && !storeId.equals(s.getStoreId())) {
                continue;
            }
            for (Product p : products) {
                if (category != null && !category.equalsIgnoreCase(p.getCategory())) {
                    continue;
                }
                List<BatchItem> bs = grouped.getOrDefault(s.getStoreId() + "|" + p.getSkuId(), List.of());
                if (bs.isEmpty()) {
                    rows.add(new InventorySummaryItem(s.getStoreId(), s.getName(), p.getSkuId(),
                            p.getName(), p.getCategory(), p.getUnit(), 0, 0, null, null, "OUT_OF_STOCK"));
                } else {
                    int onHand = bs.stream().mapToInt(BatchItem::qtyRemaining).sum();
                    LocalDate nearest = bs.stream().map(BatchItem::expiryDate)
                            .min(Comparator.naturalOrder()).orElseThrow();
                    long days = ChronoUnit.DAYS.between(ref, nearest);
                    rows.add(new InventorySummaryItem(s.getStoreId(), s.getName(), p.getSkuId(),
                            p.getName(), p.getCategory(), p.getUnit(), onHand, bs.size(),
                            nearest, days, freshness(days)));
                }
            }
        }
        return rows;
    }
}
