package com.zerowaste.grocery.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.LocalDate;

@Entity
@Table(name = "sales")
public class Sale {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "sale_id")
    private Long saleId;

    @Column(name = "sale_date")
    private LocalDate saleDate;

    @Column(name = "store_id")
    private String storeId;

    @Column(name = "sku_id")
    private String skuId;

    @Column(name = "qty_sold")
    private Integer qtySold;

    @Column(name = "unit_price")
    private BigDecimal unitPrice;

    @Column(name = "revenue")
    private BigDecimal revenue;

    @Column(name = "promo_id")
    private String promoId;

    public Long getSaleId() { return saleId; }
    public LocalDate getSaleDate() { return saleDate; }
    public String getStoreId() { return storeId; }
    public String getSkuId() { return skuId; }
    public Integer getQtySold() { return qtySold; }
    public BigDecimal getUnitPrice() { return unitPrice; }
    public BigDecimal getRevenue() { return revenue; }
    public String getPromoId() { return promoId; }
}
