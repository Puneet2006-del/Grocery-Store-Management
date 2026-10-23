package com.zerowaste.grocery.service;

import com.zerowaste.grocery.exception.ResourceNotFoundException;
import com.zerowaste.grocery.security.UserContext;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Service;

/** Which shops the signed-in shopkeeper may see. Everything else is reported as "not found". */
@Service
public class AccessService {

    private final JdbcClient jdbc;

    public AccessService(DataSource dataSource) {
        this.jdbc = JdbcClient.create(dataSource);
    }

    public long userId() {
        return UserContext.require().userId();
    }

    public List<String> storeIds() {
        return jdbc.sql("SELECT store_id FROM stores WHERE owner_id = :u ORDER BY store_id")
                .param("u", userId()).query((rs, i) -> rs.getString("store_id")).list();
    }

    public boolean owns(String storeId) {
        return storeId != null && storeIds().contains(storeId);
    }

    public void requireStore(String storeId) {
        if (!owns(storeId)) {
            throw new ResourceNotFoundException("Store not found: " + storeId);
        }
    }
}
