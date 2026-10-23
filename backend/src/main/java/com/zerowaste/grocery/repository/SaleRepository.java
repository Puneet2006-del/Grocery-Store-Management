package com.zerowaste.grocery.repository;

import com.zerowaste.grocery.entity.Sale;
import java.time.LocalDate;
import java.util.Collection;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface SaleRepository extends JpaRepository<Sale, Long> {

    @Query("""
            select s from Sale s
            where s.storeId in :storeIds
              and (:skuId is null or s.skuId = :skuId)
              and s.saleDate between :fromDate and :toDate
            order by s.saleDate desc, s.storeId asc, s.skuId asc
            """)
    Page<Sale> search(@Param("storeIds") Collection<String> storeIds,
                      @Param("skuId") String skuId,
                      @Param("fromDate") LocalDate fromDate,
                      @Param("toDate") LocalDate toDate,
                      Pageable pageable);
}
