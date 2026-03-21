export default function Loading() {
  return (
    <div className="p-6 space-y-4 animate-pulse">
      <div className="h-4 bg-gray-100 rounded w-48" />
      <div className="grid grid-cols-3 gap-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 h-32" />
        ))}
      </div>
      <div className="bg-white rounded-xl border border-gray-200 p-5 h-48" />
      <div className="grid grid-cols-4 gap-3">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="bg-white rounded-lg border border-gray-200 p-3 h-20" />
        ))}
      </div>
    </div>
  );
}
