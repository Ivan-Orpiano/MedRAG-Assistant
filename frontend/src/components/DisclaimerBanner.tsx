import { DISCLAIMER } from "@/lib/settings";

export default function DisclaimerBanner() {
  return (
    <div className="flex w-full items-center gap-2 rounded-lg bg-amber-100 p-3 text-amber-900">
      <span aria-hidden className="text-xl">⚠️</span>
      <p className="text-sm">{DISCLAIMER}</p>
    </div>
  );
}
