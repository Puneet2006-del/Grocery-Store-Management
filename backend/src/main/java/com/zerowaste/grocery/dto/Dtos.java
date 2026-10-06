package com.zerowaste.grocery.dto;

import com.zerowaste.grocery.entity.Product;
import com.zerowaste.grocery.entity.Sale;
import com.zerowaste.grocery.entity.Store;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.springframework.data.domain.Page;

/** All API response shapes in one place. */
public final class Dtos {

    private Dtos() {
    }

    public record StoreDto(String storeId, String name, String city, String type,
                           BigDecimal lat, BigDecimal lon) {
        public static StoreDto from(Store s) {
            return new StoreDto(s.getStoreId(), s.getName(), s.getCity(), s.getType(),
                    s.getLat(), s.getLon());
        }
    }

    public record ProductDto(String skuId, String name, String category, Integer shelfLifeDays,
                             String unit, BigDecimal cost, BigDecimal basePrice, String storageTemp) {
        public static ProductDto from(Product p) {
            return new ProductDto(p.getSkuId(), p.getName(), p.getCategory(), p.getShelfLifeDays(),
                    p.getUnit(), p.getCost(), p.getBasePrice(), p.getStorageTemp());
        }
    }

    /** One batch on the shelf, with days left until it expires. */
    public record BatchItem(String batchId, String storeId, String storeName, String skuId,
                            String productName, String category, String unit,
                            LocalDate receivedDate, LocalDate expiryDate,
                            Integer qtyReceived, Integer qtyRemaining,
                            long daysToExpiry, String status) {
    }

    /** One row per store and SKU: total on hand and the nearest expiry. */
    public record InventorySummaryItem(String storeId, String storeName, String skuId,
                                       String productName, String category, String unit,
                                       int onHandQty, int batchCount,
                                       LocalDate nearestExpiry, Long daysToExpiry, String status) {
    }

    public record SaleDto(Long saleId, LocalDate saleDate, String storeId, String skuId,
                          Integer qtySold, BigDecimal unitPrice, BigDecimal revenue, String promoId) {
        public static SaleDto from(Sale s) {
            return new SaleDto(s.getSaleId(), s.getSaleDate(), s.getStoreId(), s.getSkuId(),
                    s.getQtySold(), s.getUnitPrice(), s.getRevenue(), s.getPromoId());
        }
    }

    public record PageResponse<T>(List<T> content, int page, int size,
                                  long totalElements, int totalPages) {
        public static <T> PageResponse<T> of(Page<T> p) {
            return new PageResponse<>(p.getContent(), p.getNumber(), p.getSize(),
                    p.getTotalElements(), p.getTotalPages());
        }
    }
}
