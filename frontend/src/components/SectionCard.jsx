export default function SectionCard({ title, icon, children, count }) {
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mb-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-gray-800 flex items-center gap-2">
          <span>{icon}</span> {title}
        </h3>
        {typeof count === "number" && (
          <span className="text-xs bg-gray-100 text-gray-500 px-2 py-1 rounded-full">
            {count}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}