import { PracticeJurisdictionForm } from "@/components/settings/PracticeJurisdictionForm";

export default function SettingsPage() {
  return (
    <main>
      <h1 className="text-xl font-semibold">Settings</h1>
      <div className="mt-6">
        <PracticeJurisdictionForm />
      </div>
    </main>
  );
}
