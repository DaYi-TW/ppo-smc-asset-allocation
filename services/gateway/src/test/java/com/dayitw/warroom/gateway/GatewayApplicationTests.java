package com.dayitw.warroom.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
        // 測試時不真連 Redis；用 lazy connect 避免 context load 失敗
        "spring.data.redis.url=redis://localhost:65530/0",
        "spring.data.redis.lettuce.client-options.auto-reconnect=false"
})
class GatewayApplicationTests {

    @Test
    void contextLoads() {
        // smoke test：Spring context 能成功 wire 起所有 bean
    }
}
