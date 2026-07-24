import { useState, useEffect } from 'react';
import { useI18n } from '@/src/lib/i18n';
import { toast } from 'sonner';
import { Button, Card, CardHeader, CardBody, CardTitle, Input, Badge, Modal } from '@/src/components/bird';
import { Select } from '@/src/components/bird/Select';
import {
  Box, Tag, GitBranch, Lock, Package, Plus, Search,
  Upload, ChevronRight, Trash2, RefreshCw, X, Download,
} from 'lucide-react';
import {
  listSkills, getSkill, createSkill, listSkillVersions, getSkillTags,
  addSkillTag, publishSkill, acquireSkillLock, releaseSkillLock,
  getSkillDependencies, downloadSkill, type SkillResponse, type VersionResponse
} from '@/lib/api-client';
import { cn } from '@/lib/utils';

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

const API_BASE = '/api/v1';

// ============================================================
// Component
// ============================================================

export function SkillManagementBird() {
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
      const data = await listSkills();
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
      const [verData, tagData] = await Promise.all([
        listSkillVersions(skillName),
        getSkillTags(skillName),
      ]);
      setVersions(verData.items || []);
      setTags(tagData.items || []);
      setDeps([]);
    } catch (e) {
      console.error('loadVersions:', e);
    }
  };

  // Create skill
  const handleCreate = async () => {
    if (!createName.trim()) return;
    try {
      const created = await createSkill({ name: createName.trim(), description: createDesc, category: createCategory });
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
      await addSkillTag(selectedSkill.name, tagName);
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
      await acquireSkillLock(selectedSkill.name, parseInt(lockUser));
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
      const d = await getSkillDependencies(skillName);
      setDeps(d.dependencies || []);
    } catch (e) {
      console.error('loadDeps:', e);
    }
  };

  // Resolve version
  const getVersionBadge = (skill: SkillInfo) => {
    if (skill.stable_version) return { text: `stable: ${skill.stable_version}`, color: 'success' as const };
    if (skill.latest_version) return { text: `v${skill.latest_version}`, color: 'primary' as const };
    return { text: 'No versions', color: 'neutral' as const };
  };

  const filteredSkills = skills.filter(s =>
    !searchQuery || s.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#f9fafb]">
      {/* Header - Bird 风格 */}
      <header className="h-[60px] px-6 bg-white flex items-center justify-between shrink-0 border-b border-[#e5e7eb]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#ede9fe] flex items-center justify-center">
            <Package className="w-5 h-5 text-[#7c3aed]" />
          </div>
          <h1 className="text-[18px] font-semibold text-[#111827]">
            {t('skill.title')}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            className="text-[13px] rounded-xl"
            onClick={() => setShowCreate(true)}
            icon={<Plus className="w-4 h-4" />}
          >
            {t('skill.create')}
          </Button>
          <Button
            className="text-[13px] rounded-xl bg-[#7c3aed] hover:bg-[#6d28d9] text-white"
            onClick={() => { loadSkills(); toast.success('Refreshed'); }}
            disabled={loading}
            icon={<RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />}
          >
            {t('skill.refresh')}
          </Button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Skill List */}
        <div className="w-[340px] shrink-0 bg-white border-r border-[#e5e7eb] flex flex-col">
          <div className="p-4 border-b border-[#e5e7eb]">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#9ca3af]" />
              <Input
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder={t('skill.search')}
                className="pl-9"
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
                  className={cn(
                    "w-full text-left px-4 py-3 hover:bg-[#f9fafb] transition-colors border-b border-[#f3f4f6]",
                    isSelected && "bg-[#f5f3ff]"
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[14px] font-medium text-[#111827]">{s.name}</span>
                    <ChevronRight className="w-4 h-4 text-[#9ca3af]" />
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <Badge variant={badge.color} size="sm" className="text-[10px]">
                      {badge.text}
                    </Badge>
                    {s.version_count > 0 && (
                      <span className="text-[11px] text-[#6b7280]">{s.version_count} versions</span>
                    )}
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Details */}
        <div className="flex-1 overflow-y-auto bg-[#f9fafb]">
          {!selectedSkill ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-[#9ca3af]">
              <Package className="w-12 h-12" />
              <p className="text-[14px]">{t('skill.selectPrompt')}</p>
            </div>
          ) : (
            <div className="p-6 max-w-4xl space-y-4">
              {/* Skill Info */}
              <Card>
                <CardBody>
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h2 className="text-[16px] font-semibold text-[#111827]">{selectedSkill.name}</h2>
                      {selectedSkill.description && (
                        <p className="text-[13px] text-[#6b7280] mt-1">{selectedSkill.description}</p>
                      )}
                    </div>
                    <Button
                      className="rounded-xl bg-[#7c3aed] hover:bg-[#6d28d9] text-white"
                      onClick={() => setShowPublish(true)}
                      icon={<Upload className="w-4 h-4" />}
                    >
                      {t('skill.publish')}
                    </Button>
                  </div>
                  <div className="flex gap-3 text-[12px] text-[#6b7280]">
                    <span>Category: {selectedSkill.category}</span>
                    {selectedSkill.owner && <span>Owner: {selectedSkill.owner}</span>}
                    <span>Status: {selectedSkill.status}</span>
                  </div>
                </CardBody>
              </Card>

              {/* Versions */}
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-[#7c3aed]" />
                    <CardTitle>{t('skill.versions')}</CardTitle>
                    <Badge variant="neutral" size="sm">{versions.length}</Badge>
                  </div>
                </CardHeader>
                <CardBody className="p-0">
                  <div className="divide-y divide-[#f3f4f6] max-h-[300px] overflow-y-auto">
                    {versions.map(v => (
                      <div key={v.id} className="px-5 py-3 flex items-center justify-between hover:bg-[#f9fafb]">
                        <div>
                          <span className="text-[14px] font-mono font-medium text-[#111827]">v{v.version}</span>
                          <Badge
                            variant={v.status === 'released' ? 'success' : 'neutral'}
                            size="sm"
                            className="ml-2 text-[10px]"
                          >
                            {v.status}
                          </Badge>
                          {v.changelog && (
                            <p className="text-[12px] text-[#6b7280] mt-0.5 truncate max-w-[400px]">{v.changelog}</p>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-[#9ca3af] font-mono">{v.package_hash?.slice(0, 8)}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDownload(selectedSkill.name, v.version)}
                            icon={<Download className="w-3.5 h-3.5" />}
                          >
                            Download
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => loadDeps(selectedSkill.name, v.version)}
                            icon={<Box className="w-3.5 h-3.5" />}
                          >
                            {t('skill.deps')}
                          </Button>
                        </div>
                      </div>
                    ))}
                    {versions.length === 0 && (
                      <div className="px-5 py-8 text-center text-[13px] text-[#6b7280]">
                        {t('skill.noVersions')}
                      </div>
                    )}
                  </div>
                </CardBody>
              </Card>

              {/* Tags & Locks */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Tags */}
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Tag className="w-4 h-4 text-[#7c3aed]" />
                        <CardTitle>{t('skill.tags')}</CardTitle>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowTag(true)}
                        icon={<Plus className="w-3.5 h-3.5" />}
                      >
                        {t('skill.addTag')}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardBody className="p-3 space-y-2 max-h-[200px] overflow-y-auto">
                    {tags.map(tg => (
                      <div key={tg.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#f9fafb]">
                        <span className="text-[13px] font-mono font-medium text-[#7c3aed]">{tg.tag_name}</span>
                        <span className="text-[12px] text-[#6b7280]">→ v{tg.version}</span>
                      </div>
                    ))}
                    {tags.length === 0 && (
                      <div className="text-center text-[12px] text-[#9ca3af] py-4">{t('skill.noTags')}</div>
                    )}
                  </CardBody>
                </Card>

                {/* Locks */}
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Lock className="w-4 h-4 text-[#7c3aed]" />
                        <CardTitle>{t('skill.locks')}</CardTitle>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setShowLock(true)}
                        icon={<Plus className="w-3.5 h-3.5" />}
                      >
                        {t('skill.addLock')}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardBody className="p-3 text-center text-[12px] text-[#6b7280] py-4">
                    {t('skill.lockHint')}
                  </CardBody>
                </Card>
              </div>

              {/* Dependency Tree */}
              <Card>
                <CardHeader>
                  <div className="flex items-center gap-2">
                    <Box className="w-4 h-4 text-[#7c3aed]" />
                    <CardTitle>{t('skill.depTree')}</CardTitle>
                    {deps.length > 0 && <Badge variant="neutral" size="sm">{deps.length}</Badge>}
                  </div>
                </CardHeader>
                <CardBody>
                  {deps.length > 0 ? (
                    <div className="space-y-2">
                      {deps.map((d, i) => (
                        <div key={i} className="flex items-center gap-2 py-1.5">
                          <span className="font-medium text-[#7c3aed]">{d.dep_skill_name}</span>
                          <span className="text-[#6b7280] text-[12px]">{d.constraint}</span>
                          <ChevronRight className="w-3 h-3 text-[#9ca3af]" />
                          <span className="font-mono text-[#10b981] text-[13px]">{d.resolved_version}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center text-[12px] text-[#6b7280] py-4">
                      Click <b className="text-[#111827]">Deps</b> on a version to view its dependency tree.
                    </div>
                  )}
                </CardBody>
              </Card>
            </div>
          )}
        </div>
      </div>

      {/* Create Modal */}
      <Modal
        open={showCreate}
        onOpenChange={setShowCreate}
        title={t('skill.create')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreate(false)}>Cancel</Button>
            <Button onClick={handleCreate} disabled={!createName.trim()} className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white">
              Create
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Name *</label>
            <Input
              value={createName}
              onChange={e => setCreateName(e.target.value)}
              placeholder="my-skill"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Description</label>
            <Input
              value={createDesc}
              onChange={e => setCreateDesc(e.target.value)}
              placeholder="Brief description"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Category</label>
            <Select
              value={createCategory}
              onChange={e => setCreateCategory(e.target.value)}
              className="w-full"
            >
              {['L0', 'L1', 'L2', 'L3', 'L4'].map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </Select>
          </div>
        </div>
      </Modal>

      {/* Publish Modal */}
      <Modal
        open={showPublish}
        onOpenChange={setShowPublish}
        title={t('skill.publish')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowPublish(false)}>Cancel</Button>
            <Button onClick={handlePublish} disabled={!publishVersion || !publishFile} className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white">
              Publish
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Version (SemVer)</label>
            <Input
              value={publishVersion}
              onChange={e => setPublishVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Changelog</label>
            <Input
              value={publishChangelog}
              onChange={e => setPublishChangelog(e.target.value)}
              placeholder="Initial release"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Dependencies (JSON)</label>
            <textarea
              value={publishDeps}
              onChange={e => setPublishDeps(e.target.value)}
              placeholder={`[{"dep_skill_name":"other-skill","version_constraint":">=1.0.0"}]`}
              className="w-full text-[13px] border border-[#e5e7eb] rounded-xl px-3 py-2 h-20 resize-none focus:outline-none focus:ring-2 focus:ring-[#7c3aed]"
            />
            <span className="text-[10px] text-[#9ca3af]">JSON array, leave empty if no deps</span>
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Package File</label>
            <Input type="file" onChange={e => setPublishFile(e.target.files?.[0] || null)} />
          </div>
        </div>
      </Modal>

      {/* Tag Modal */}
      <Modal
        open={showTag}
        onOpenChange={setShowTag}
        title={t('skill.setTag')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowTag(false)}>Cancel</Button>
            <Button onClick={handleSetTag} disabled={!tagName || !tagVersion} className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white">
              Set Tag
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Tag Name</label>
            <Input
              value={tagName}
              onChange={e => setTagName(e.target.value)}
              placeholder="stable"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Target Version</label>
            <Input
              value={tagVersion}
              onChange={e => setTagVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </div>
        </div>
      </Modal>

      {/* Lock Modal */}
      <Modal
        open={showLock}
        onOpenChange={setShowLock}
        title={t('skill.setLock')}
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowLock(false)}>Cancel</Button>
            <Button onClick={handleSetLock} disabled={!lockUser || !lockVersion} className="bg-[#7c3aed] hover:bg-[#6d28d9] text-white">
              Lock
            </Button>
          </>
        }
      >
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">User ID</label>
            <Input
              value={lockUser}
              onChange={e => setLockUser(e.target.value)}
              placeholder="user_zhangsan"
            />
          </div>
          <div className="space-y-2">
            <label className="text-[12px] font-medium text-[#4b5563]">Lock Version</label>
            <Input
              value={lockVersion}
              onChange={e => setLockVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
