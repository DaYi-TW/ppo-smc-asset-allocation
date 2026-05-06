package com.dayitw.warroom.gateway.integration;

import io.swagger.parser.OpenAPIParser;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.parser.core.models.SwaggerParseResult;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "predictions.redis.enabled=false",
        "spring.data.redis.url=redis://localhost:65530/0",
        "spring.data.redis.lettuce.client-options.auto-reconnect=false",
        "inference.url=http://localhost:1"
})
@AutoConfigureMockMvc
class ContractOpenApiTest {

    @Autowired MockMvc mockMvc;

    @Test
    void apiDocs_returns200_andValidOpenApi() throws Exception {
        var body = mockMvc.perform(get("/v3/api-docs").accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();

        SwaggerParseResult parsed = new OpenAPIParser().readContents(body, null, null);
        OpenAPI api = parsed.getOpenAPI();
        assertThat(api).as("springdoc must produce parseable OpenAPI").isNotNull();
        assertThat(parsed.getMessages()).as("OpenAPI parse messages").isEmpty();

        // FR-013：四個 path 必須齊
        assertThat(api.getPaths()).containsKeys(
                "/api/v1/inference/run",
                "/api/v1/inference/latest",
                "/api/v1/inference/healthz",
                "/api/v1/predictions/stream");

        // FR-013：components.schemas 必須含三個核心 schema
        assertThat(api.getComponents().getSchemas()).containsKeys(
                "PredictionPayloadDto",
                "ErrorResponseDto",
                "HealthDto");
    }
}
