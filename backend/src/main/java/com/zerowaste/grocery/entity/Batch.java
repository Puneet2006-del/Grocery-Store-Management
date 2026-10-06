package com.zerowaste.grocery.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDate;

@Entity
@Table(name = "batches")
public class Batch {

    @Id
    @Column(name = "batch_id")
    private String batchId;

    @Column(name = "sku_id")
    private String skuId;

    @Column(name = "store_id")
    private String storeId;

    @Column(name = "received_date")
    private LocalDate receivedDate;

    @Column(name = "expiry_date")
    private LocalDate expiryDate;

    @Column(name = "qty_received")
    private Integer qtyReceived;

    @Column(name = "qty_remaining")
    private Integer qtyRemaining;

    public String getBatchId() { return batchId; }
    public String getSkuId() { return skuId; }
    public String getStoreId() { return storeId; }
    public LocalDate getReceivedDate() { return receivedDate; }
    public LocalDate getExpiryDate() { return expiryDate; }
    public Integer getQtyReceived() { return qtyReceived; }
    public Integer getQtyRemaining() { return qtyRemaining; }
}
