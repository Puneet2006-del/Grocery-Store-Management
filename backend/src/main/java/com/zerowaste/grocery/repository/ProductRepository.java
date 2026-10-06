package com.zerowaste.grocery.repository;

import com.zerowaste.grocery.entity.Product;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository extends JpaRepository<Product, String> {

    List<Product> findAllByOrderBySkuIdAsc();

    List<Product> findByCategoryIgnoreCaseOrderBySkuIdAsc(String category);
}
