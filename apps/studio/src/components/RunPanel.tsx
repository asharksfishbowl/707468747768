import React, { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { createRun, notifyUnauthorized, openRunStream } from "../api/client";
import type { CircuitDefinition, RunStatus, RunStreamMessage } from "../api/types";
import { colors, RUN_STATUS_COLOR } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing } from "../theme/spacing";
import { EmptyState } from "./EmptyState";
import { Histogram } from "./Histogram";

/** Matches services/api/app/auth.py's `authenticate_websocket` (Requirement 5,
 * Edge Case 11) — the private-range close code it sends on an invalid/expired
 * WS `?token=`. */
const WS_AUTH_FAILURE_CODE = 4401;

interface RunState {
  runId: string;
  status: RunStatus;
  histogram: Record<string, Record<string, number>> | null;
  errorMessage: string | null;
}

interface RunPanelProps {
  processorId: string;
  definition: CircuitDefinition;
  hasMeasureGate: boolean;
}

/** Run panel (Requirement 42): noisy/noiseless toggle, repetitions input,
 * Run button, live status + histogram via the run's WS stream. */
export function RunPanel({ processorId, definition, hasMeasureGate }: RunPanelProps) {
  const [noisy, setNoisy] = useState(true);
  const [repetitionsText, setRepetitionsText] = useState("100");
  const [run, setRun] = useState<RunState | null>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const repetitions = Number.parseInt(repetitionsText, 10);
  const repetitionsValid = Number.isInteger(repetitions) && repetitions >= 1 && repetitions <= 1000;
  const isInFlight = run?.status === "queued" || run?.status === "running";

  const applyMessage = useCallback((msg: RunStreamMessage) => {
    setRun((current) => {
      if (!current || current.runId !== msg.run_id) return current;
      return {
        ...current,
        status: msg.status,
        histogram: msg.result ?? msg.partial_histogram ?? current.histogram,
        errorMessage: msg.error_message ?? current.errorMessage,
      };
    });
  }, []);

  const connectStream = useCallback(
    (runId: string) => {
      wsRef.current?.close();
      openRunStream(runId).then((ws) => {
        wsRef.current = ws;
        ws.onmessage = (event) => {
          setReconnecting(false);
          applyMessage(JSON.parse(event.data));
        };
        ws.onclose = (event) => {
          // A stale socket (superseded by a newer connectStream call, e.g. a
          // fresh Run submitted before this one's close event arrived) must
          // never drive a reconnect — only the connection still current gets
          // to decide that.
          if (wsRef.current !== ws) return;

          if (event.code === WS_AUTH_FAILURE_CODE) {
            // Requirement 5/Edge Case 11: the JWT this stream was opened with
            // is no longer valid — same session-expiry handling as a REST
            // 401 (Edge Case 10), not a reconnect-worthy transient drop.
            notifyUnauthorized();
            return;
          }

          // Edge Case 8: any other unexpected close mid-run reconnects
          // immediately — the server's on-connect current-state send
          // (Requirement 34) resyncs us, no polling/delay needed.
          setRun((current) => {
            if (current && (current.status === "queued" || current.status === "running")) {
              setReconnecting(true);
              connectStream(runId);
            }
            return current;
          });
        };
      });
    },
    [applyMessage],
  );

  useEffect(() => () => wsRef.current?.close(), []);

  const submitRun = useCallback(async () => {
    setSubmitError(null);
    try {
      const { run_id, status } = await createRun({
        circuit_id: null,
        definition,
        processor_id: processorId,
        noisy,
        repetitions,
      });
      setRun({ runId: run_id, status, histogram: null, errorMessage: null });
      connectStream(run_id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to start run");
    }
  }, [connectStream, definition, noisy, processorId, repetitions]);

  const canRun = hasMeasureGate && repetitionsValid && !isInFlight;

  return (
    <View style={styles.container}>
      <View style={styles.toggleRow}>
        <Text style={styles.label}>{noisy ? "Noisy" : "Noiseless"}</Text>
        <Switch value={noisy} onValueChange={setNoisy} disabled={isInFlight} />
      </View>

      <Text style={styles.label}>Repetitions</Text>
      <TextInput
        style={styles.input}
        value={repetitionsText}
        onChangeText={setRepetitionsText}
        keyboardType="number-pad"
        editable={!isInFlight}
      />
      {!repetitionsValid && <Text style={styles.errorText}>Must be between 1 and 1000</Text>}

      <Pressable
        style={[styles.runButton, !canRun ? styles.runButtonDisabled : null]}
        disabled={!canRun}
        onPress={submitRun}
      >
        <Text style={styles.runButtonText}>Run</Text>
      </Pressable>
      {!hasMeasureGate && <Text style={styles.hintText}>Add a MEASURE gate to run</Text>}
      {submitError && <Text style={styles.errorText}>{submitError}</Text>}

      {run && (
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: RUN_STATUS_COLOR[run.status] }]} />
          <Text style={styles.label}>{run.status}</Text>
          {reconnecting && <Text style={styles.hintText}>Reconnecting…</Text>}
        </View>
      )}

      {run?.status === "error" ? (
        <EmptyState
          tone="error"
          icon="⚠"
          message={run.errorMessage ?? "The run failed."}
          ctaLabel="Retry Run"
          onPressCta={submitRun}
        />
      ) : (
        run && <Histogram definition={definition} histogram={run.histogram} status={run.status} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { padding: spacing.sm, gap: spacing.xs },
  toggleRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  label: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
  input: {
    fontFamily: fonts.mono,
    fontSize: fontSizes.md,
    color: colors.textPrimary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.xs,
    minHeight: MIN_TOUCH_TARGET,
  },
  errorText: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.error },
  hintText: { fontFamily: fonts.sans, fontSize: fontSizes.xs, color: colors.textMuted },
  runButton: {
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: radii.sm,
    backgroundColor: colors.gateRotation,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.xs,
  },
  runButtonDisabled: { opacity: 0.4 },
  runButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.background, fontWeight: "700" },
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.xs },
  statusDot: { width: 10, height: 10, borderRadius: 5 },
});
