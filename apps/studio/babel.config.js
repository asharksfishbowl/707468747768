module.exports = function (api) {
  api.cache(true);
  return {
    presets: ["babel-preset-expo"],
    // react-native-worklets/plugin must be listed last (Reanimated 4's worklet
    // transform moved into react-native-worklets) — used by GateGrid/Toast's
    // withTiming-driven state transitions (design spec's Animation section).
    plugins: ["react-native-worklets/plugin"],
  };
};
