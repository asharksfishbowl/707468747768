import React, { useCallback, useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { createCircuit, listPresets, listProcessors, updateCircuit } from "../api/client";
import type { CircuitDefinition, CircuitFull, Processor } from "../api/types";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { GateGrid } from "../components/GateGrid";
import { GatePalette } from "../components/GatePalette";
import { RunPanel } from "../components/RunPanel";
import { Toast } from "../components/Toast";
import { useCircuitBuilder } from "../hooks/useCircuitBuilder";
import { colors } from "../theme/colors";
import { fonts, fontSizes } from "../theme/typography";
import { MIN_TOUCH_TARGET, radii, spacing, WEB_LAYOUT_BREAKPOINT } from "../theme/spacing";

const PRESET_NAMES = ["Hello Qubit", "Bell State", "GHZ State", "Superposition"];

interface BuilderScreenProps {
  loadRequest: CircuitFull | null;
  onConsumeLoadRequest: () => void;
}

export function BuilderScreen({ loadRequest, onConsumeLoadRequest }: BuilderScreenProps) {
  const { width } = useWindowDimensions();
  const isWebLayout = width >= WEB_LAYOUT_BREAKPOINT;

  const [processors, setProcessors] = useState<Processor[]>([]);
  const [selectedProcessorId, setSelectedProcessorId] = useState<string | null>(null);
  const [presets, setPresets] = useState<CircuitDefinition[]>([]);
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const [savedCircuit, setSavedCircuit] = useState<{ id: string; name: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<
    { type: "loadPreset"; definition: CircuitDefinition } | { type: "switchProcessor"; processorId: string } | null
  >(null);
  const [nameModal, setNameModal] = useState<{ mode: "save" | "saveAs"; initialName: string } | null>(null);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);
  const [mobileTab, setMobileTab] = useState<"build" | "run">("build");

  useEffect(() => {
    listProcessors().then((list) => {
      setProcessors(list);
      setSelectedProcessorId((current) => current ?? list[0]?.id ?? null);
    });
  }, []);

  const processor = processors.find((p) => p.id === selectedProcessorId);
  const topology = processor?.topology ?? { qubits: [], pairs: [] };
  const builder = useCircuitBuilder(selectedProcessorId ?? "", topology);

  useEffect(() => {
    if (!loadRequest) return;
    builder.loadDefinition(loadRequest.definition);
    setSelectedProcessorId(loadRequest.processor_id);
    setSavedCircuit({ id: loadRequest.id, name: loadRequest.name });
    onConsumeLoadRequest();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadRequest]);

  const openPresetMenu = useCallback(() => {
    if (!selectedProcessorId) return;
    listPresets(selectedProcessorId).then(setPresets);
    setPresetMenuOpen(true);
  }, [selectedProcessorId]);

  const requestLoadPreset = (definition: CircuitDefinition) => {
    setPresetMenuOpen(false);
    if (builder.isEmpty) {
      builder.loadDefinition(definition);
      setSavedCircuit(null);
    } else {
      setConfirmAction({ type: "loadPreset", definition });
    }
  };

  const requestSwitchProcessor = (processorId: string) => {
    if (processorId === selectedProcessorId) return;
    if (builder.isEmpty) {
      setSelectedProcessorId(processorId);
    } else {
      setConfirmAction({ type: "switchProcessor", processorId });
    }
  };

  const confirmDialogProps =
    confirmAction?.type === "loadPreset"
      ? { title: "Load this preset?", body: "Your current circuit will be replaced.", confirmLabel: "Load Preset" }
      : confirmAction?.type === "switchProcessor"
        ? {
            title: "Switch processor?",
            body: "Placed gates may no longer be valid on the new topology.",
            confirmLabel: "Switch",
          }
        : null;

  const handleConfirm = () => {
    if (confirmAction?.type === "loadPreset") {
      builder.loadDefinition(confirmAction.definition);
      setSavedCircuit(null);
    } else if (confirmAction?.type === "switchProcessor") {
      setSelectedProcessorId(confirmAction.processorId);
    }
    setConfirmAction(null);
  };

  const doSave = async (name: string) => {
    try {
      if (nameModal?.mode === "save" && savedCircuit) {
        const updated = await updateCircuit(savedCircuit.id, { definition: builder.definition });
        setSavedCircuit({ id: updated.id, name: updated.name });
      } else {
        const created = await createCircuit({ name, definition: builder.definition, is_public: false });
        setSavedCircuit({ id: created.id, name: created.name });
      }
      setToast({ message: "Saved", tone: "success" });
    } catch (e) {
      setToast({ message: e instanceof Error ? e.message : "Save failed", tone: "error" });
    }
    setNameModal(null);
  };

  const handleSavePress = () => {
    if (savedCircuit) {
      doSave(savedCircuit.name);
    } else {
      setNameModal({ mode: "save", initialName: "" });
    }
  };

  const handleSaveAsPress = () => {
    setNameModal({ mode: "saveAs", initialName: savedCircuit ? `${savedCircuit.name} copy` : "" });
  };

  if (!selectedProcessorId) {
    return <View style={styles.screen} />;
  }

  const toolbar = (
    <View style={styles.toolbar}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.processorPicker}>
        {processors.map((p) => (
          <Pressable
            key={p.id}
            onPress={() => requestSwitchProcessor(p.id)}
            style={[styles.processorChip, p.id === selectedProcessorId ? styles.processorChipActive : null]}
          >
            <Text style={styles.processorChipText}>{p.id}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <Pressable style={styles.toolbarButton} onPress={openPresetMenu}>
        <Text style={styles.toolbarButtonText}>Load preset</Text>
      </Pressable>
      <Pressable style={styles.toolbarButton} onPress={handleSavePress}>
        <Text style={styles.toolbarButtonText}>Save</Text>
      </Pressable>
      <Pressable style={styles.toolbarButton} onPress={handleSaveAsPress}>
        <Text style={styles.toolbarButtonText}>Save As</Text>
      </Pressable>
    </View>
  );

  const grid = <GateGrid topology={topology} builder={builder} />;
  const runPanel = (
    <RunPanel processorId={selectedProcessorId} definition={builder.definition} hasMeasureGate={builder.hasMeasureGate} />
  );

  return (
    <View style={styles.screen}>
      {toolbar}

      {isWebLayout ? (
        <View style={styles.webLayout}>
          <GatePalette variant="rail" armedGate={builder.armedGate} onArm={builder.armGate} />
          <View style={styles.gridArea}>{grid}</View>
          <ScrollView style={styles.runRail}>{runPanel}</ScrollView>
        </View>
      ) : (
        <View style={styles.mobileLayout}>
          <View style={{ flex: 1, display: mobileTab === "build" ? "flex" : "none" }}>{grid}</View>
          <ScrollView style={{ flex: 1, display: mobileTab === "run" ? "flex" : "none" }}>{runPanel}</ScrollView>
          <GatePalette variant="drawer" armedGate={builder.armedGate} onArm={builder.armGate} />
          <View style={styles.mobileTabBar}>
            <Pressable style={styles.mobileTabButton} onPress={() => setMobileTab("build")}>
              <Text style={mobileTab === "build" ? styles.mobileTabActive : styles.mobileTabText}>Build</Text>
            </Pressable>
            <Pressable style={styles.mobileTabButton} onPress={() => setMobileTab("run")}>
              <Text style={mobileTab === "run" ? styles.mobileTabActive : styles.mobileTabText}>Run</Text>
            </Pressable>
          </View>
        </View>
      )}

      <Toast message={builder.toast?.message ?? null} tone={builder.toast?.tone} onDismiss={builder.dismissToast} />
      <Toast message={toast?.message ?? null} tone={toast?.tone} onDismiss={() => setToast(null)} />

      <Modal visible={presetMenuOpen} transparent animationType="fade" onRequestClose={() => setPresetMenuOpen(false)}>
        <Pressable style={styles.scrim} onPress={() => setPresetMenuOpen(false)}>
          <View style={styles.presetMenu}>
            {presets.map((def, i) => (
              <Pressable key={PRESET_NAMES[i]} style={styles.presetItem} onPress={() => requestLoadPreset(def)}>
                <Text style={styles.presetItemText}>{PRESET_NAMES[i]}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>

      {confirmDialogProps && (
        <ConfirmDialog
          visible
          title={confirmDialogProps.title}
          body={confirmDialogProps.body}
          confirmLabel={confirmDialogProps.confirmLabel}
          variant="accent"
          onConfirm={handleConfirm}
          onCancel={() => setConfirmAction(null)}
        />
      )}

      <NameEntryModal
        visible={nameModal !== null}
        initialName={nameModal?.initialName ?? ""}
        onCancel={() => setNameModal(null)}
        onConfirm={doSave}
      />
    </View>
  );
}

function NameEntryModal({
  visible,
  initialName,
  onCancel,
  onConfirm,
}: {
  visible: boolean;
  initialName: string;
  onCancel: () => void;
  onConfirm: (name: string) => void;
}) {
  const [name, setName] = useState(initialName);
  useEffect(() => setName(initialName), [initialName, visible]);

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onCancel}>
      <Pressable style={styles.scrim} onPress={onCancel}>
        <Pressable style={styles.nameModalCard} onPress={() => {}}>
          <Text style={styles.presetItemText}>Name your circuit</Text>
          <TextInput style={styles.nameInput} value={name} onChangeText={setName} autoFocus />
          <View style={styles.nameModalRow}>
            <Pressable style={styles.toolbarButton} onPress={onCancel}>
              <Text style={styles.toolbarButtonText}>Cancel</Text>
            </Pressable>
            <Pressable
              style={[styles.toolbarButton, { backgroundColor: colors.gateRotation }]}
              disabled={!name}
              onPress={() => onConfirm(name)}
            >
              <Text style={[styles.toolbarButtonText, { color: colors.background }]}>Save</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    padding: spacing.xs,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  processorPicker: { flexDirection: "row", flexGrow: 0 },
  processorChip: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.xs,
    justifyContent: "center",
    borderRadius: radii.sm,
    marginRight: spacing.xs / 2,
    borderWidth: 1,
    borderColor: colors.border,
  },
  processorChipActive: { borderColor: colors.gateRotation, backgroundColor: colors.surfaceElevated },
  processorChipText: { fontFamily: fonts.mono, fontSize: fontSizes.xs, color: colors.textPrimary },
  toolbarButton: {
    minHeight: MIN_TOUCH_TARGET,
    paddingHorizontal: spacing.xs,
    justifyContent: "center",
    borderRadius: radii.sm,
    backgroundColor: colors.surfaceElevated,
  },
  toolbarButtonText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary },
  webLayout: { flex: 1, flexDirection: "row" },
  gridArea: { flex: 1 },
  runRail: { width: 260, borderLeftWidth: 1, borderLeftColor: colors.border },
  mobileLayout: { flex: 1 },
  mobileTabBar: { flexDirection: "row", borderTopWidth: 1, borderTopColor: colors.border },
  mobileTabButton: { flex: 1, minHeight: MIN_TOUCH_TARGET, alignItems: "center", justifyContent: "center" },
  mobileTabText: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textMuted },
  mobileTabActive: { fontFamily: fonts.sans, fontSize: fontSizes.sm, color: colors.textPrimary, fontWeight: "700" },
  scrim: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", alignItems: "center", justifyContent: "center" },
  presetMenu: { backgroundColor: colors.surfaceElevated, borderRadius: radii.lg, padding: spacing.sm, minWidth: 220 },
  presetItem: { minHeight: MIN_TOUCH_TARGET, justifyContent: "center" },
  presetItemText: { fontFamily: fonts.sans, fontSize: fontSizes.md, color: colors.textPrimary },
  nameModalCard: { backgroundColor: colors.surfaceElevated, borderRadius: radii.lg, padding: spacing.sm, minWidth: 280, gap: spacing.xs },
  nameInput: {
    fontFamily: fonts.sans,
    fontSize: fontSizes.md,
    color: colors.textPrimary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.xs,
    minHeight: MIN_TOUCH_TARGET,
  },
  nameModalRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.xs },
});
