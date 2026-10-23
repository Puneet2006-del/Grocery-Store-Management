package com.zerowaste.grocery.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "stores")
public class Store {

    @Id
    @Column(name = "store_id")
    private String storeId;

    @Column(name = "name")
    private String name;

    @Column(name = "city")
    private String city;

    @Column(name = "type")
    private String type;

    @Column(name = "lat")
    private BigDecimal lat;

    @Column(name = "lon")
    private BigDecimal lon;

    @Column(name = "status")
    private String status;

    @Column(name = "status_message")
    private String statusMessage;

    @Column(name = "size_factor")
    private BigDecimal sizeFactor;

    public String getStoreId() { return storeId; }
    public String getName() { return name; }
    public String getCity() { return city; }
    public String getType() { return type; }
    public BigDecimal getLat() { return lat; }
    public BigDecimal getLon() { return lon; }
    public String getStatus() { return status; }
    public String getStatusMessage() { return statusMessage; }
    public BigDecimal getSizeFactor() { return sizeFactor; }
}
