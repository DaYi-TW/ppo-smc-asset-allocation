package com.dayitw.warroom.gateway.service;

import com.dayitw.warroom.gateway.exception.InferenceBusyException;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.PredictionNotReadyException;
import com.github.tomakehurst.wiremock.junit5.WireMockExtension;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.web.client.RestClient;

import java.time.Duration;

import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.post;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InferenceClientTest {

    @RegisterExtension
    static WireMockExtension wm = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    private InferenceClient newClient() {
        var rc = RestClient.builder().baseUrl(wm.baseUrl()).build();
        return new InferenceClient(rc, Duration.ofSeconds(90), Duration.ofSeconds(5), Duration.ofSeconds(2));
    }

    @Test
    void runInference_parsesSnakeCaseResponse() {
        wm.stubFor(post(urlEqualTo("/infer/run")).willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                        {
                          "as_of_date": "2026-04-28",
                          "next_trading_day_target": "next session",
                          "policy_path": "/app/p.zip",
                          "deterministic": true,
                          "target_weights": {"NVDA": 0.1, "CASH": 0.9},
                          "weights_capped": false,
                          "renormalized": false,
                          "context": {"data_root": "data/raw", "include_smc": true, "n_warmup_steps": 100, "current_nav_at_as_of": 1.0},
                          "triggered_by": "manual",
                          "inference_id": "550e8400-e29b-41d4-a716-446655440000",
                          "inferred_at_utc": "2026-05-06T00:00:00Z"
                        }
                        """)));

        var client = newClient();
        var dto = client.runInference();
        assertThat(dto.asOfDate()).isEqualTo("2026-04-28");
        assertThat(dto.targetWeights()).containsEntry("NVDA", 0.1);
        assertThat(dto.context().currentNavAtAsOf()).isEqualTo(1.0);
        assertThat(dto.triggeredBy()).isEqualTo("manual");
    }

    @Test
    void runInference_409_throwsBusy() {
        wm.stubFor(post(urlEqualTo("/infer/run")).willReturn(aResponse().withStatus(409)));
        var client = newClient();
        assertThatThrownBy(client::runInference).isInstanceOf(InferenceBusyException.class);
    }

    @Test
    void runInference_5xx_throwsServiceException() {
        wm.stubFor(post(urlEqualTo("/infer/run")).willReturn(aResponse().withStatus(503)));
        var client = newClient();
        assertThatThrownBy(client::runInference).isInstanceOf(InferenceServiceException.class);
    }

    @Test
    void getLatest_404_throwsPredictionNotReady() {
        wm.stubFor(get(urlEqualTo("/infer/latest")).willReturn(aResponse().withStatus(404)));
        var client = newClient();
        assertThatThrownBy(client::getLatest).isInstanceOf(PredictionNotReadyException.class);
    }

    @Test
    void getHealthz_passesThrough() {
        wm.stubFor(get(urlEqualTo("/healthz")).willReturn(aResponse()
                .withStatus(200)
                .withHeader("Content-Type", "application/json")
                .withBody("""
                        {"status":"ok","uptime_seconds":42,"policy_loaded":true,"redis_reachable":true,
                         "last_inference_at_utc":null,"next_scheduled_run_utc":null}
                        """)));
        var client = newClient();
        var dto = client.getHealthz();
        assertThat(dto.status()).isEqualTo("ok");
        assertThat(dto.policyLoaded()).isTrue();
    }
}
