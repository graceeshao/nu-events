/**
 * App header with Northwestern branding.
 */

export function Header() {
  return (
    <header className="bg-nu-purple text-white shadow-lg">
      <div className="max-w-6xl mx-auto px-4 py-5 flex items-center gap-4">
        <div className="text-3xl">🟣</div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">NU Events</h1>
          <p className="text-nu-purple-200 text-sm">
            What&apos;s happening at Northwestern
          </p>
        </div>
      </div>
    </header>
  );
}
