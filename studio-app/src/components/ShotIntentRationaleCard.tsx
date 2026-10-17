import { getShotIntentRationale, type ShotIntentInput } from '../lib/shotIntentRationale';

type ShotIntentRationaleCardProps = {
  shot?: ShotIntentInput | null;
  testId: string;
};

export default function ShotIntentRationaleCard({ shot, testId }: ShotIntentRationaleCardProps) {
  const rationale = getShotIntentRationale(shot);
  return (
    <div
      data-testid={testId}
      className="mt-3 rounded-lg border border-amber-300/25 bg-amber-400/5 px-3 py-2"
    >
      <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-200">
        Why this shot matters
      </div>
      <p className="mt-1 text-sm leading-relaxed text-zinc-200">{rationale}</p>
    </div>
  );
}
