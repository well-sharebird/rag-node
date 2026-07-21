import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Box, Tag, GitBranch, Lock, Package, Plus, Search,
  Upload, ChevronRight, Trash2, RefreshCw, X, Download,
} from 'lucide-react';

const API_BASE = '/api/v1';

// ============================================================
// Types
// ============================================================

interface SkillInfo {
  id: number;
  name: string;
  description?: string;
  category: string;
  owner?: string;
  status: string;
  latest_version?: string;
  stable_version?: string;
  version_count: number;
  created_at: string;
}

interface VersionInfo {
  id: number;
  skill_id: number;
  version: string;
  package_hash: string;
  changelog?: string;
  released_by?: string;
  status: string;
  created_at: string;
}

interface TagInfo {
  id: number;
  tag_name: string;
  version?: string;
}

interface DepInfo {
  dep_skill_name: string;
  constraint: string;
  resolved_version: string;
}

// ============================================================
// Component
// ============================================================

export function SkillManagement() {
  const { t } = useI18n();

  // State
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [selectedSkill, setSelectedSkill] = useState<SkillInfo | null>(null);
  const [versions, setVersions] = useState<VersionInfo[]>([]);
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [deps, setDeps] = useState<DepInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Create dialog
  const [showCreate, setShowCreate] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [createCategory, setCreateCategory] = useState('L1');

  // Publish dialog
  const [showPublish, setShowPublish] = useState(false);
  const [publishVersion, setPublishVersion] = useState('');
  const [publishChangelog, setPublishChangelog] = useState('');
  const [publishDeps, setPublishDeps] = useState('');
  const [publishFile, setPublishFile] = useState<File | null>(null);

  // Tag dialog
  const [showTag, setShowTag] = useState(false);
  const [tagName, setTagName] = useState('');
  const [tagVersion, setTagVersion] = useState('');

  // Lock dialog
  const [showLock, setShowLock] = useState(false);
  const [lockUser, setLockUser] = useState('');
  const [lockVersion, setLockVersion] = useState('');

  // Load skills
  const loadSkills = async () => {
    try {
      const res = await fetch(`${API_BASE}/skills`);
      if (!res.ok) throw new Error('Failed');
      const data = await res.json();
      setSkills(data.items || []);
    } catch (e) {
      console.error('loadSkills:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSkills(); }, []);

  // Load versions when skill selected
  const loadVersions = async (skillName: string) => {
    try {
      const [verRes, tagRes] = await Promise.all([
        fetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}/versions`),
        fetch(`${API_BASE}/skills/${encodeURIComponent(skillName)}/tags`),
      ]);
      if (verRes.ok) {
        const v = await verRes.json();
        setVersions(v.items || []);
      }
      if (tagRes.ok) {
        const tg = await tagRes.json();
        setTags(tg.items || []);
      }
      setDeps([]);
    } catch (e) {
      console.error('loadVersions:', e);
    }
  };

  // Create skill
  const handleCreate = async () => {
    if (!createName.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/skills`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: createName.trim(), description: createDesc, category: createCategory }),
      });
      if (!res.ok) throw new Error('Failed');
      const created = await res.json();
      toast.success(`Created: ${created.name}`);
      setShowCreate(false);
      setCreateName('');
      setCreateDesc('');
      setCreateCategory('L1');
      loadSkills();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  // Download
  const handleDownload = (skillName: string, version?: string) => {
    const url = version
      ? `${API_BASE}/skills/${encodeURIComponent(skillName)}/download?version=${encodeURIComponent(version)}`
      : `${API_BASE}/skills/${encodeURIComponent(skillName)}/download`;
    window.open(url, '_blank');
  };

  const selectSkill = (skill: SkillInfo) => {
    setSelectedSkill(skill);
    loadVersions(skill.name);
  };

  // Publish
  const handlePublish = async () => {
    if (!publishVersion || !publishFile || !selectedSkill) return;
    const formData = new FormData();
    formData.append('skill_name', selectedSkill.name);
    formData.append('version', publishVersion);
    formData.append('changelog', publishChangelog);
    if (publishDeps.trim()) {
      formData.append('dependencies', publishDeps.trim());
    }
    formData.append('file', publishFile);

    try {
      const res = await fetch(`${API_BASE}/skills/publish`, {
        method: 'POST', body: formData,
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Publish failed');
      }
      toast.success(`Published ${selectedSkill.name}@${publishVersion}`);
      setShowPublish(false);
      setPublishVersion('');
      setPublishChangelog('');
      setPublishDeps('');
      setPublishFile(null);
      loadVersions(selectedSkill.name);
      loadSkills();
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  // Set tag
  const handleSetTag = async () => {
    if (!tagName || !tagVersion || !selectedSkill) return;
    try {
      const res = await fetch(`${API_BASE}/skills/${encodeURIComponent(selectedSkill.name)}/tags`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tag_name: tagName, version: tagVersion }),
      });
      if (!res.ok) throw new Error('Failed');
      toast.success(`Tag ${tagName} -> ${tagVersion}`);
      setShowTag(false);
      setTagName('');
      setTagVersion('');
      loadVersions(selectedSkill.name);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  // Set lock
  const handleSetLock = async () => {
    if (!lockUser || !lockVersion || !selectedSkill) return;
    try {
      const res = await fetch(`${API_BASE}/skills/${encodeURIComponent(selectedSkill.name)}/locks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: lockUser, version: lockVersion }),
      });
      if (!res.ok) throw new Error('Failed');
      toast.success(`Locked ${lockUser} -> ${selectedSkill.name}@${lockVersion}`);
      setShowLock(false);
      setLockUser('');
      setLockVersion('');
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  // Load dependencies
  const loadDeps = async (skillName: string, version: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/skills/${encodeURIComponent(skillName)}/deps?version=${encodeURIComponent(version)}`
      );
      if (res.ok) {
        const d = await res.json();
        setDeps(d.dependencies || []);
      }
    } catch (e) {
      console.error('loadDeps:', e);
    }
  };

  // Resolve version
  const getVersionBadge = (skill: SkillInfo) => {
    if (skill.stable_version) return { text: `stable: ${skill.stable_version}`, color: '#22c55e' };
    if (skill.latest_version) return { text: `v${skill.latest_version}`, color: '#534ab7' };
    return { text: 'No versions', color: '#9b9b9b' };
  };

  const filteredSkills = skills.filter(s =>
    !searchQuery || s.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Header */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e5e5]">
        <div className="flex items-center gap-3">
          <Package className="w-5 h-5" style={{ color: '#534ab7' }} />
          <h1 className="text-[18px] font-semibold text-[#1a1a1a]">
            {t('skill.title')}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="text-[13px] h-9 rounded-lg"
            onClick={() => setShowCreate(true)}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            {t('skill.create')}
          </Button>
          <Button
            className="text-[13px] h-9 rounded-lg"
            style={{ background: '#534ab7' }}
            onClick={() => { loadSkills(); toast.success('Refreshed'); }}
            disabled={loading}
          >
            <RefreshCw className="w-4 h-4 mr-1.5" />
            {t('skill.refresh')}
          </Button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Skill List */}
        <div className="w-[340px] shrink-0 bg-white border-r border-[#e5e5e5] flex flex-col">
          <div className="p-4">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#9b9b9b]" />
              <Input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder={t('skill.search')}
                className="pl-9 h-9 text-[13px] rounded-lg"
                style={{ borderColor: '#e2e1dd' }}
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {filteredSkills.map(s => {
              const badge = getVersionBadge(s);
              const isSelected = selectedSkill?.id === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => selectSkill(s)}
                  className="w-full text-left px-4 py-3 hover:bg-[#f7f7f5] transition-colors border-b border-[#f0f0f0]"
                  style={isSelected ? { background: '#eeedfe' } : {}}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] font-medium text-[#1a1a1a]">{s.name}</span>
                    <ChevronRight className="w-4 h-4 text-[#9b9b9b]" />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[11px] px-1.5 py-0.5 rounded" style={{
                      background: `${badge.color}15`, color: badge.color, fontSize: '11px',
                    }}>
                      {badge.text}
                    </span>
                    {s.version_count > 0 && (
                      <span className="text-[11px] text-[#9b9b9b]">{s.version_count} versions</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Details */}
        <div className="flex-1 overflow-y-auto bg-[#f7f7f7]">
          {!selectedSkill ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-[#9b9b9b]">
              <Package className="w-12 h-12" />
              <p className="text-[14px]">{t('skill.selectPrompt')}</p>
            </div>
          ) : (
            <div className="p-6 max-w-4xl">
              {/* Skill Info */}
              <div className="bg-white rounded-xl p-5 border border-[#e5e5e5] mb-4">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h2 className="text-[16px] font-semibold">{selectedSkill.name}</h2>
                    {selectedSkill.description && (
                      <p className="text-[13px] text-[#6b6b6b] mt-1">{selectedSkill.description}</p>
                    )}
                  </div>
                  <Button
                    className="text-[13px] h-8 rounded-lg"
                    style={{ background: '#534ab7' }}
                    onClick={() => setShowPublish(true)}
                  >
                    <Upload className="w-3.5 h-3.5 mr-1" />
                    {t('skill.publish')}
                  </Button>
                </div>
                <div className="flex gap-3 text-[12px] text-[#9b9b9b]">
                  <span>Category: {selectedSkill.category}</span>
                  {selectedSkill.owner && <span>Owner: {selectedSkill.owner}</span>}
                  <span>Status: {selectedSkill.status}</span>
                </div>
              </div>

              {/* Versions */}
              <div className="bg-white rounded-xl border border-[#e5e5e5] mb-4">
                <div className="px-5 py-3 border-b border-[#e5e5e5] flex items-center gap-2">
                  <GitBranch className="w-4 h-4 text-[#534ab7]" />
                  <h3 className="text-[14px] font-semibold">{t('skill.versions')}</h3>
                  <span className="text-[12px] text-[#9b9b9b]">({versions.length})</span>
                </div>
                <div className="divide-y divide-[#f0f0f0] max-h-[300px] overflow-y-auto">
                  {versions.map(v => (
                    <div key={v.id} className="px-5 py-3 flex items-center justify-between hover:bg-[#fafaf9]">
                      <div>
                        <span className="text-[14px] font-mono font-medium">v{v.version}</span>
                        <span className={`ml-2 text-[11px] px-1.5 py-0.5 rounded ${
                          v.status === 'released' ? 'bg-green-50 text-green-600' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {v.status}
                        </span>
                        {v.changelog && (
                          <p className="text-[12px] text-[#9b9b9b] mt-0.5 truncate max-w-[400px]">{v.changelog}</p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[11px] text-[#9b9b9b] font-mono">{v.package_hash?.slice(0, 8)}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-[11px]"
                          onClick={() => handleDownload(selectedSkill.name, v.version)}
                        >
                          <Download className="w-3 h-3 mr-1" />
                          Download
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 text-[11px]"
                          onClick={() => loadDeps(selectedSkill.name, v.version)}
                        >
                          <Box className="w-3 h-3 mr-1" />
                          {t('skill.deps')}
                        </Button>
                      </div>
                    </div>
                  ))}
                  {versions.length === 0 && (
                    <div className="px-5 py-8 text-center text-[13px] text-[#9b9b9b]">
                      {t('skill.noVersions')}
                    </div>
                  )}
                </div>
              </div>

              {/* Tags & Locks */}
              <div className="grid grid-cols-2 gap-4 mb-4">
                {/* Tags */}
                <div className="bg-white rounded-xl border border-[#e5e5e5]">
                  <div className="px-5 py-3 border-b border-[#e5e5e5] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Tag className="w-4 h-4 text-[#534ab7]" />
                      <h3 className="text-[14px] font-semibold">{t('skill.tags')}</h3>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-[11px]"
                      onClick={() => setShowTag(true)}
                    >
                      <Plus className="w-3 h-3 mr-1" />
                      {t('skill.addTag')}
                    </Button>
                  </div>
                  <div className="p-3 space-y-2 max-h-[200px] overflow-y-auto">
                    {tags.map(tg => (
                      <div key={tg.id} className="flex items-center justify-between px-2 py-1.5 rounded bg-[#f7f7f5]">
                        <span className="text-[13px] font-mono font-medium text-[#534ab7]">{tg.tag_name}</span>
                        <span className="text-[12px] text-[#9b9b9b]">→ v{tg.version}</span>
                      </div>
                    ))}
                    {tags.length === 0 && (
                      <div className="text-center text-[12px] text-[#9b9b9b] py-4">{t('skill.noTags')}</div>
                    )}
                  </div>
                </div>

                {/* Locks */}
                <div className="bg-white rounded-xl border border-[#e5e5e5]">
                  <div className="px-5 py-3 border-b border-[#e5e5e5] flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Lock className="w-4 h-4 text-[#534ab7]" />
                      <h3 className="text-[14px] font-semibold">{t('skill.locks')}</h3>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-[11px]"
                      onClick={() => setShowLock(true)}
                    >
                      <Plus className="w-3 h-3 mr-1" />
                      {t('skill.addLock')}
                    </Button>
                  </div>
                  <div className="p-3 text-center text-[12px] text-[#9b9b9b] py-4">
                    {t('skill.lockHint')}
                  </div>
                </div>
              </div>

              {/* Dependency Tree */}
              {/* Dependency Tree */}
              <div className="bg-white rounded-xl border border-[#e5e5e5]">
                <div className="px-5 py-3 border-b border-[#e5e5e5] flex items-center gap-2">
                  <Box className="w-4 h-4 text-[#534ab7]" />
                  <h3 className="text-[14px] font-semibold">{t('skill.depTree')}</h3>
                  {deps.length > 0 && <span className="text-[12px] text-[#9b9b9b]">({deps.length})</span>}
                </div>
                <div className="p-4">
                  {deps.length > 0 ? (
                    deps.map((d, i) => (
                      <div key={i} className="flex items-center gap-2 py-1.5 text-[13px]">
                        <span className="font-medium text-[#534ab7]">{d.dep_skill_name}</span>
                        <span className="text-[#9b9b9b] text-[12px]">{d.constraint}</span>
                        <ChevronRight className="w-3 h-3 text-[#9b9b9b]" />
                        <span className="font-mono text-[#22c55e]">{d.resolved_version}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-center text-[12px] text-[#9b9b9b] py-4">
                      Click <b>Deps</b> on a version to view its dependency tree.<br />
                      Add dependencies in the <b>Publish Dialog</b> to declare them.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create Dialog */}
      {showCreate && (
        <DialogOverlay onClose={() => setShowCreate(false)} title={t('skill.create')}>
          <div className="space-y-3">
            <div>
              <label className="text-[12px] font-medium">Name *</label>
              <Input value={createName} onChange={e => setCreateName(e.target.value)}
                placeholder="my-skill" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Description</label>
              <Input value={createDesc} onChange={e => setCreateDesc(e.target.value)}
                placeholder="Brief description" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Category</label>
              <select value={createCategory} onChange={e => setCreateCategory(e.target.value)}
                className="mt-1 w-full text-[13px] border rounded-lg px-3 py-2" style={{ borderColor: '#e2e1dd' }}>
                {['L0','L1','L2','L3','L4'].map(c => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowCreate(false)} className="text-[13px]">Cancel</Button>
              <Button onClick={handleCreate} className="text-[13px]" style={{ background: '#534ab7' }}
                disabled={!createName.trim()}>Create</Button>
            </div>
          </div>
        </DialogOverlay>
      )}

      {/* Publish Dialog */}
      {showPublish && (
        <DialogOverlay onClose={() => setShowPublish(false)} title={t('skill.publish')}>
          <div className="space-y-3">
            <div>
              <label className="text-[12px] font-medium">Version (SemVer)</label>
              <Input value={publishVersion} onChange={e => setPublishVersion(e.target.value)}
                placeholder="1.0.0" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Changelog</label>
              <Input value={publishChangelog} onChange={e => setPublishChangelog(e.target.value)}
                placeholder="Initial release" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Dependencies (JSON)</label>
              <textarea value={publishDeps} onChange={e => setPublishDeps(e.target.value)}
                placeholder={`[{"dep_skill_name":"other-skill","version_constraint":">=1.0.0"}]`}
                className="mt-1 w-full text-[13px] border rounded-lg px-3 py-2 h-20 resize-none"
                style={{ borderColor: '#e2e1dd' }} />
              <span className="text-[10px] text-[#9b9b9b]">JSON array, leave empty if no deps</span>
            </div>
            <div>
              <label className="text-[12px] font-medium">Package File</label>
              <Input type="file" onChange={e => setPublishFile(e.target.files?.[0] || null)}
                className="mt-1 text-[13px]" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowPublish(false)} className="text-[13px]">
                Cancel
              </Button>
              <Button onClick={handlePublish} className="text-[13px]" style={{ background: '#534ab7' }}
                disabled={!publishVersion || !publishFile}>
                Publish
              </Button>
            </div>
          </div>
        </DialogOverlay>
      )}

      {/* Tag Dialog */}
      {showTag && (
        <DialogOverlay onClose={() => setShowTag(false)} title={t('skill.setTag')}>
          <div className="space-y-3">
            <div>
              <label className="text-[12px] font-medium">Tag Name</label>
              <Input value={tagName} onChange={e => setTagName(e.target.value)}
                placeholder="stable" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Target Version</label>
              <Input value={tagVersion} onChange={e => setTagVersion(e.target.value)}
                placeholder="1.0.0" className="mt-1 text-[13px]" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowTag(false)} className="text-[13px]">Cancel</Button>
              <Button onClick={handleSetTag} className="text-[13px]" style={{ background: '#534ab7' }}
                disabled={!tagName || !tagVersion}>Set Tag</Button>
            </div>
          </div>
        </DialogOverlay>
      )}

      {/* Lock Dialog */}
      {showLock && (
        <DialogOverlay onClose={() => setShowLock(false)} title={t('skill.setLock')}>
          <div className="space-y-3">
            <div>
              <label className="text-[12px] font-medium">User ID</label>
              <Input value={lockUser} onChange={e => setLockUser(e.target.value)}
                placeholder="user_zhangsan" className="mt-1 text-[13px]" />
            </div>
            <div>
              <label className="text-[12px] font-medium">Lock Version</label>
              <Input value={lockVersion} onChange={e => setLockVersion(e.target.value)}
                placeholder="1.0.0" className="mt-1 text-[13px]" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowLock(false)} className="text-[13px]">Cancel</Button>
              <Button onClick={handleSetLock} className="text-[13px]" style={{ background: '#534ab7' }}
                disabled={!lockUser || !lockVersion}>Lock</Button>
            </div>
          </div>
        </DialogOverlay>
      )}
    </div>
  );
}

// Simple dialog overlay
function DialogOverlay({ children, onClose, title }: {
  children: React.ReactNode; onClose: () => void; title: string;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.3)' }}>
      <div className="bg-white rounded-xl p-6 w-[480px] shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-[15px] font-semibold">{title}</h2>
          <button onClick={onClose} className="hover:bg-gray-100 p-1 rounded">
            <X className="w-4 h-4" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
