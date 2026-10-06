package com.zerowaste.grocery.repository;

import com.zerowaste.grocery.entity.Store;
import org.springframework.data.jpa.repository.JpaRepository;

public interface StoreRepository extends JpaRepository<Store, String> {
}
