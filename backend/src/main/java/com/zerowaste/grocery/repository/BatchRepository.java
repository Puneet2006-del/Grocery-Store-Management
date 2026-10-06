package com.zerowaste.grocery.repository;

import com.zerowaste.grocery.entity.Batch;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BatchRepository extends JpaRepository<Batch, String> {

    /** Batches that still have stock on the shelf, oldest expiry first. */
    List<Batch> findByQtyRemainingGreaterThanOrderByExpiryDateAsc(Integer qty);
}
