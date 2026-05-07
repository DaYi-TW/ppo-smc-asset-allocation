package com.dayitw.warroom.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "predictions.redis.enabled=false",
        "spring.data.redis.url=redis://localhost:65530/0",
        "spring.data.redis.lettuce.client-options.auto-reconnect=false",
        "inference.url=http://localhost:1"
})
class GatewayApplicationTests {

    @Test
    void contextLoads() {
        // smoke test：Spring context 能成功 wire 起所有 bean（不啟動 Redis listener）
    }
}
