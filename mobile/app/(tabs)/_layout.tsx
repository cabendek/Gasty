import { Tabs } from "expo-router";

export default function TabsLayout() {
  return (
    <Tabs>
      <Tabs.Screen name="index" options={{ title: "Dashboard" }} />
      <Tabs.Screen name="transactions" options={{ title: "Transacciones" }} />
      <Tabs.Screen name="settings" options={{ title: "Configuración" }} />
    </Tabs>
  );
}
