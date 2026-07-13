import { useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  MapPin,
  Phone,
  Mail,
  Globe,
  Star,
  Clock,
  Tag,
  MessageSquareText,
  ImageOff,
} from "lucide-react";
import { useSearchContext } from "../context/SearchContext";

const SOCIAL_STYLE = {
  facebook: "text-blue-600 bg-blue-50 hover:bg-blue-100",
  instagram: "text-pink-600 bg-pink-50 hover:bg-pink-100",
  twitter: "text-sky-600 bg-sky-50 hover:bg-sky-100",
  linkedin: "text-blue-700 bg-blue-50 hover:bg-blue-100",
  youtube: "text-red-600 bg-red-50 hover:bg-red-100",
};

function BusinessDetailPage() {
  const { slug } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { filtered } = useSearchContext();

  const biz =
    location.state?.business ||
    filtered.find(
      (b) => encodeURIComponent(b.name.toLowerCase().replace(/\s+/g, "-")) === slug
    );

  const currentIndex = biz ? filtered.findIndex((b) => b.place_id === biz.place_id) : -1;
  const prevBiz = currentIndex > 0 ? filtered[currentIndex - 1] : null;
  const nextBiz = currentIndex >= 0 && currentIndex < filtered.length - 1 ? filtered[currentIndex + 1] : null;

  const goTo = (target) => {
    if (!target) return;
    const targetSlug = encodeURIComponent(target.name.toLowerCase().replace(/\s+/g, "-"));
    navigate(`/business/${targetSlug}`, { state: { business: target } });
  };

  if (!biz) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-rose-50 px-4">
        <div className="text-center bg-white/90 backdrop-blur rounded-2xl shadow-xl border border-slate-100 p-8 max-w-md">
          <p className="text-slate-800 font-semibold mb-2">No business data to show</p>
          <p className="text-slate-500 text-sm mb-6">
            This page only works when you get here by clicking a result on the search page —
            direct links aren't supported yet since results aren't saved to a database.
          </p>
          <button
            onClick={() => navigate("/")}
            className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-sm px-5 py-3 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" /> Back to search
          </button>
        </div>
      </div>
    );
  }

  const hoursList = biz.opening_hours
    ? biz.opening_hours.split("|").map((line) => line.trim()).filter(Boolean)
    : null;

  return (
    <div className="relative w-full min-h-screen overflow-hidden bg-gradient-to-br from-indigo-50 via-white to-rose-50">
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="animate-blob absolute -top-24 -left-24 h-72 w-72 rounded-full bg-indigo-300/30 blur-3xl" />
        <div className="animate-blob absolute bottom-0 right-0 h-96 w-96 rounded-full bg-rose-200/30 blur-3xl" />
      </div>

      <div className="relative px-4 py-8 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-3xl">
          <div className="flex items-center justify-between mb-6">
            <button
              onClick={() => navigate("/")}
              className="inline-flex items-center gap-2 text-slate-500 hover:text-indigo-600 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-400 rounded"
            >
              <ArrowLeft className="h-4 w-4" /> Back to results
            </button>

            {filtered.length > 0 && currentIndex >= 0 && (
              <span className="text-xs text-slate-400">
                {currentIndex + 1} of {filtered.length}
              </span>
            )}
          </div>

          <div className="bg-white/90 backdrop-blur-xl rounded-3xl shadow-xl shadow-indigo-100 border border-white/60 p-6 sm:p-8 mb-6">
            <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
              <div>
                <h1 className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight mb-2">
                  {biz.name}
                </h1>
                {biz.category && (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold px-3 py-1.5">
                    <Tag className="h-3.5 w-3.5" /> {biz.category}
                  </span>
                )}
              </div>

              {biz.rating !== null && biz.rating !== undefined && (
                <div className="flex items-center gap-1.5 rounded-2xl bg-amber-50 border border-amber-100 px-4 py-2.5">
                  <Star className="h-5 w-5 fill-amber-400 text-amber-400" />
                  <span className="text-lg font-bold text-amber-700">{biz.rating}</span>
                  <span className="text-xs text-amber-600">
                    ({biz.reviews ?? 0} review{biz.reviews === 1 ? "" : "s"})
                  </span>
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-6">
            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <MapPin className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Address</span>
              </div>
              <p className="text-sm text-slate-600 leading-relaxed">{biz.address || "Not available"}</p>
            </div>

            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Phone className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Phone</span>
              </div>
              {biz.phone ? (
                <a href={`tel:${biz.phone}`} className="text-sm text-indigo-600 hover:underline">
                  {biz.phone}
                </a>
              ) : (
                <p className="text-sm text-slate-400">Not available</p>
              )}
            </div>

            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Mail className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Email</span>
              </div>
              {biz.email ? (
                <a href={`mailto:${biz.email}`} className="text-sm text-indigo-600 hover:underline break-all">
                  {biz.email}
                </a>
              ) : (
                <p className="text-sm text-slate-400">Not available</p>
              )}
            </div>

            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5">
              <div className="flex items-center gap-2 mb-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Globe className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Website</span>
              </div>
              {biz.website ? (
                <a
                  href={biz.website}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm text-indigo-600 hover:underline break-all"
                >
                  {biz.website}
                </a>
              ) : (
                <p className="text-sm text-slate-400">Not available</p>
              )}
            </div>
          </div>

          <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5 sm:p-6 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                <ImageOff className="h-4 w-4 text-indigo-600" />
              </span>
              <span className="text-sm font-semibold text-slate-800">Photos</span>
            </div>
            {biz.images && biz.images.length > 0 ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {biz.images.map((src, i) => (
                  <a
                    key={i}
                    href={src}
                    target="_blank"
                    rel="noreferrer"
                    className="block aspect-square rounded-xl overflow-hidden bg-slate-100 hover:opacity-90 transition-opacity"
                  >
                    <img
                      src={src}
                      alt={`${biz.name} photo ${i + 1}`}
                      loading="lazy"
                      onError={(e) => { e.currentTarget.closest("a").style.display = "none"; }}
                      className="w-full h-full object-cover"
                    />
                  </a>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-400">No photos available for this business.</p>
            )}
          </div>

          {biz.social_links && Object.keys(biz.social_links).length > 0 && (
            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5 sm:p-6 mb-6">
              <div className="flex items-center gap-2 mb-4">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Globe className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Social media</span>
              </div>
              <div className="flex flex-wrap gap-3">
                {Object.entries(biz.social_links).map(([platform, url]) => {
                  const style = SOCIAL_STYLE[platform] || "text-slate-600 bg-slate-50 hover:bg-slate-100";
                  return (
                    <a
                      key={platform}
                      href={url}
                      target="_blank"
                      rel="noreferrer"
                      className={`inline-flex items-center gap-2 rounded-xl border border-transparent px-4 py-2.5 text-sm font-medium capitalize transition-colors ${style}`}
                    >
                      <Globe className="h-4 w-4" /> {platform}
                    </a>
                  );
                })}
              </div>
            </div>
          )}

          {hoursList && hoursList.length > 0 && (
            <div className="bg-white/90 backdrop-blur rounded-2xl shadow-md shadow-slate-200/50 border border-slate-100 p-5 sm:p-6 mb-6">
              <div className="flex items-center gap-2 mb-4">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-50">
                  <Clock className="h-4 w-4 text-indigo-600" />
                </span>
                <span className="text-sm font-semibold text-slate-800">Opening hours</span>
              </div>
              <ul className="space-y-2">
                {hoursList.map((line, i) => (
                  <li
                    key={i}
                    className="flex items-center justify-between text-sm text-slate-600 border-b border-slate-50 last:border-0 pb-2 last:pb-0"
                  >
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!biz.website && !biz.phone && (
            <div className="bg-amber-50 border border-amber-100 rounded-2xl p-5 flex items-start gap-3 mb-6">
              <MessageSquareText className="h-5 w-5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-sm text-amber-700">
                This business has no listed website or phone number — that often makes it a
                strong lead for outreach.
              </p>
            </div>
          )}

          {(prevBiz || nextBiz) && (
            <div className="flex items-center justify-between gap-3">
              <button
                onClick={() => goTo(prevBiz)}
                disabled={!prevBiz}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-white/90 backdrop-blur border border-slate-100 shadow-md shadow-slate-200/50 px-4 py-3 text-sm font-medium text-slate-600 hover:text-indigo-600 hover:border-indigo-200 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                <ArrowLeft className="h-4 w-4" /> Previous
              </button>
              <button
                onClick={() => goTo(nextBiz)}
                disabled={!nextBiz}
                className="flex-1 inline-flex items-center justify-center gap-2 rounded-xl bg-white/90 backdrop-blur border border-slate-100 shadow-md shadow-slate-200/50 px-4 py-3 text-sm font-medium text-slate-600 hover:text-indigo-600 hover:border-indigo-200 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
              >
                Next <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default BusinessDetailPage;