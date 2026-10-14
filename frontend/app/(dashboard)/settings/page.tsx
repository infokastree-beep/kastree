import { PracticeJurisdictionForm } from "@/components/settings/PracticeJurisdictionForm";
import { PracticeLetterheadForm } from "@/components/settings/PracticeLetterheadForm";

export default function SettingsPage() {
  return (
    <main>
      <h1 className="text-xl font-semibold">Settings</h1>
      <div className="mt-6">
        <PracticeJurisdictionForm />
        <PracticeLetterheadForm />
      </div>
    </main>
  );
}
