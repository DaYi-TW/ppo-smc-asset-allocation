package com.dayitw.warroom.gateway.controller;

import com.dayitw.warroom.gateway.dto.LiveTrackingStatusDto;
import com.dayitw.warroom.gateway.dto.RefreshAcceptedDto;
import com.dayitw.warroom.gateway.exception.InferenceServiceException;
import com.dayitw.warroom.gateway.exception.LiveRefreshConflictException;
import com.dayitw.warroom.gateway.service.EpisodeClient;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Feature 010 T031 — gateway live endpoints contract tests。
 *
 * 4 個 flows：
 *   (a) GET /live/status pass-through 200
 *   (b) POST /live/refresh 202 + accepted body
 *   (c) 005 回 409 → gateway pass-through 409 + body verbatim
 *       （critical：FR-016 verbatim — running_pid 等欄位禁止丟失）
 *   (d) 005 不可達 → gateway 503
 */
@WebMvcTest(EpisodeController.class)
class EpisodeControllerLiveTest {

    @Autowired MockMvc mockMvc;
    @MockBean EpisodeClient episodeClient;

    @Test
    void liveStatus_returnsPassThroughDto() throws Exception {
        var dto = new LiveTrackingStatusDto(
                "2026-05-08T14:00:00Z",
                "2026-05-07",
                1,
                false,
                null);
        when(episodeClient.getLiveStatus()).thenReturn(dto);

        mockMvc.perform(get("/api/v1/episodes/live/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.last_updated").value("2026-05-08T14:00:00Z"))
                .andExpect(jsonPath("$.last_frame_date").value("2026-05-07"))
                .andExpect(jsonPath("$.data_lag_days").value(1))
                .andExpect(jsonPath("$.is_running").value(false))
                .andExpect(jsonPath("$.last_error").doesNotExist());
    }

    @Test
    void liveRefresh_returns202_withAcceptedBody() throws Exception {
        var dto = new RefreshAcceptedDto(
                true,
                "550e8400-e29b-41d4-a716-446655440000",
                8,
                "/api/v1/episodes/live/status");
        when(episodeClient.triggerLiveRefresh()).thenReturn(dto);

        mockMvc.perform(post("/api/v1/episodes/live/refresh"))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.accepted").value(true))
                .andExpect(jsonPath("$.pipeline_id")
                        .value("550e8400-e29b-41d4-a716-446655440000"))
                .andExpect(jsonPath("$.estimated_duration_seconds").value(8))
                .andExpect(jsonPath("$.poll_status_url")
                        .value("/api/v1/episodes/live/status"));
    }

    @Test
    void liveRefresh_409_passesThroughBodyVerbatim() throws Exception {
        // Critical FR-016: 005 回 409 + 完整 body，gateway 必須原樣透傳。
        // 不能走 GlobalExceptionHandler 的 ErrorResponseDto 重映射 — 否則
        // running_pid / running_started_at 會遺失。
        ObjectMapper mapper = new ObjectMapper();
        var payload = mapper.readTree("""
                {"detail":"pipeline already running",
                 "running_pid":12345,
                 "running_started_at":"2026-05-08T14:00:01Z",
                 "poll_status_url":"/api/v1/episodes/live/status"}""");
        when(episodeClient.triggerLiveRefresh())
                .thenThrow(new LiveRefreshConflictException(payload));

        mockMvc.perform(post("/api/v1/episodes/live/refresh"))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.detail").value("pipeline already running"))
                .andExpect(jsonPath("$.running_pid").value(12345))
                .andExpect(jsonPath("$.running_started_at")
                        .value("2026-05-08T14:00:01Z"))
                .andExpect(jsonPath("$.poll_status_url")
                        .value("/api/v1/episodes/live/status"));
    }

    @Test
    void liveStatus_503_when005Unreachable() throws Exception {
        when(episodeClient.getLiveStatus())
                .thenThrow(new InferenceServiceException("upstream down", new RuntimeException()));

        mockMvc.perform(get("/api/v1/episodes/live/status"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"));
    }

    @Test
    void liveRefresh_503_when005Unreachable() throws Exception {
        when(episodeClient.triggerLiveRefresh())
                .thenThrow(new InferenceServiceException("upstream down", new RuntimeException()));

        mockMvc.perform(post("/api/v1/episodes/live/refresh"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error").value("InferenceServiceUnavailable"));
    }
}
