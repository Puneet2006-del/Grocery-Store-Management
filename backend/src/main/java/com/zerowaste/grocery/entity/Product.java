package com.zerowaste.grocery.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @Column(name = "sku_id")
    private String skuId;

    @Column(name = "name")
    private String name;

    @Column(name = "category")
    private String category;

    @Column(name = "shelf_life_days")
    private Integer shelfLifeDays;

    @Column(name = "unit")
    private String unit;

    @Column(name = "cost")
    private BigDecimal cost;

    @Column(name = "base_price")
    private BigDecimal basePrice;

    @Column(name = "storage_temp")
    private String storageTemp;

    public String getSkuId() { return skuId; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public Integer getShelfLifeDays() { return shelfLifeDays; }
    public String getUnit() { return unit; }
    public BigDecimal getCost() { return cost; }
    public BigDecimal getBasePrice() { return basePrice; }
    public String getStorageTemp() { return storageTemp; }
}
