package com.dayitw.warroom.gateway.config;

import com.dayitw.warroom.gateway.controller.InferenceController;
import com.dayitw.warroom.gateway.service.InferenceClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InferenceController.class)
@Import(CorsConfig.class)
@TestPropertySource(properties = "cors.allowed-origins=http://localhost:5173,https://app.example.com")
class CorsConfigTest {

    @Autowired MockMvc mockMvc;
    @MockBean InferenceClient inferenceClient;

    @Test
    void preflight_allowedOrigin_returns200_withAllowOriginHeader() throws Exception {
        mockMvc.perform(options("/api/v1/inference/run")
                        .header("Origin", "http://localhost:5173")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isOk())
                .andExpect(header().string("Access-Control-Allow-Origin", "http://localhost:5173"));
    }

    @Test
    void preflight_disallowedOrigin_returns403() throws Exception {
        mockMvc.perform(options("/api/v1/inference/run")
                        .header("Origin", "http://evil.example.com")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isForbidden());
    }
}
