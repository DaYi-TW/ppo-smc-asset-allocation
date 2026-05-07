package com.dayitw.warroom.gateway.integration;

import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Schema;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 確保 Gateway DTO 對 005 OpenAPI 的 PredictionPayload schema 欄位數一致。
 * 005 改了欄位 → 本測試 fail，提示同步 DTO（spec FR-014）.
 */
@SpringBootTest(properties = {
        "predictions.redis.enabled=false",
        "spring.data.redis.url=redis://localhost:65530/0",
        "spring.data.redis.lettuce.client-options.auto-reconnect=false",
        "inference.url=http://localhost:1"
})
@AutoConfigureMockMvc
class SchemaParityTest {

    @Autowired MockMvc mockMvc;

    @Test
    void predictionPayload_fieldCount_matches005() throws Exception {
        // 1) Gateway 動態 OpenAPI（snake→camel 對映後的欄位）
        var gatewayJson = mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
        OpenAPI gateway = new OpenAPIParser().readContents(gatewayJson, null, null).getOpenAPI();
        Schema<?> gwPayload = gateway.getComponents().getSchemas().get("PredictionPayloadDto");
        Schema<?> gwContext = gateway.getComponents().getSchemas().get("ContextDto");
        assertThat(gwPayload).isNotNull();
        assertThat(gwContext).isNotNull();

        // 2) 005 spec OpenAPI（從 repo root 找）
        Path inferenceContract = locate005Contract();
        OpenAPI inference = new OpenAPIParser()
                .readContents(Files.readString(inferenceContract), null, null)
                .getOpenAPI();
        Schema<?> infPayload = inference.getComponents().getSchemas().get("PredictionPayload");
        Schema<?> infContext = inference.getComponents().getSchemas().get("PredictionContext");
        assertThat(infPayload).isNotNull();
        assertThat(infContext).isNotNull();

        // 3) 欄位數一致（Gateway DTO 必須完整 cover 005 schema）
        assertThat(propertyKeys(gwPayload))
                .as("PredictionPayload 欄位數需與 005 一致；005 加欄位請同步 PredictionPayloadDto")
                .hasSameSizeAs(propertyKeys(infPayload));
        assertThat(propertyKeys(gwContext))
                .as("PredictionContext 欄位數需與 005 一致；005 加欄位請同步 ContextDto")
                .hasSameSizeAs(propertyKeys(infContext));
    }

    private static Set<String> propertyKeys(Schema<?> schema) {
        Map<String, Schema> props = schema.getProperties();
        if (props == null) return Set.of();
        return props.keySet().stream().collect(Collectors.toUnmodifiableSet());
    }

    private static Path locate005Contract() {
        // 從 services/gateway/ 出發往上找 repo root，再 cd 到 specs/005-...
        Path cwd = Path.of("").toAbsolutePath();
        for (int i = 0; i < 5; i++) {
            Path candidate = cwd.resolve("specs/005-inference-service/contracts/openapi.yaml");
            if (Files.exists(candidate)) return candidate;
            cwd = cwd.getParent();
            if (cwd == null) break;
        }
        throw new IllegalStateException("無法定位 specs/005-inference-service/contracts/openapi.yaml");
    }
}
