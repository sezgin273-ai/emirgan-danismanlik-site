<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';

admin_require_login();

$content = load_content();
$csrf = admin_csrf_token();
$backups = list_content_backups();
$flash = null;

admin_start_session();
if (!empty($_SESSION['admin_flash'])) {
    $flash = $_SESSION['admin_flash'];
    unset($_SESSION['admin_flash']);
}

$serviceIcons = ['strategy', 'legal', 'finance', 'feasibility', 'realestate', 'trade', 'governance'];
$badgeIcons = ['energy', 'realestate', 'trade', 'construction', 'investment'];
$sectionLabels = [
    'hero' => 'Ana Sayfa (Hero)',
    'intro' => 'Kısa Tanıtım',
    'services' => 'Hizmetler',
    'about' => 'Hakkımızda',
    'team' => 'Ekibimiz',
    'contact' => 'İletişim',
];
?>
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İçerik Yönetimi — Emirgan Admin</title>
    <link rel="stylesheet" href="/admin/assets/admin.css">
</head>
<body>
<div class="admin-shell">
    <div class="admin-topbar">
        <h1>İçerik Yönetimi</h1>
        <form method="post" action="/admin/actions.php">
            <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
            <input type="hidden" name="action" value="logout">
            <button type="submit" class="admin-btn">Çıkış</button>
        </form>
    </div>

    <?php if ($flash): ?>
        <p class="admin-alert admin-alert--<?= e($flash['type'] === 'ok' ? 'ok' : 'error') ?>" role="status">
            <?= e($flash['message']) ?>
        </p>
    <?php endif; ?>

    <nav class="admin-nav" aria-label="Panel bölümleri">
        <a href="#seo">SEO</a>
        <a href="#sections">Bölümler</a>
        <a href="#hero">Hero</a>
        <a href="#intro">Tanıtım</a>
        <a href="#about">Hakkımızda</a>
        <a href="#services">Hizmetler</a>
        <a href="#team">Ekip</a>
        <a href="#contact">İletişim</a>
        <a href="#kvkk">KVKK</a>
        <a href="#media">Görseller</a>
        <a href="#backups">Yedekler</a>
        <a href="/" target="_blank" rel="noopener">Siteyi aç</a>
    </nav>

    <form method="post" action="/admin/actions.php" class="admin-form" id="content-form">
        <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
        <input type="hidden" name="action" value="save_content">

        <section class="admin-card" id="seo">
            <h2>SEO ve Site</h2>
            <div class="admin-grid-2">
                <div>
                    <label for="site-title">Site başlığı</label>
                    <input type="text" id="site-title" name="content[site][title]" value="<?= e($content['site']['title']) ?>">
                </div>
                <div>
                    <label for="site-lang">Dil kodu</label>
                    <input type="text" id="site-lang" name="content[site][lang]" value="<?= e($content['site']['lang']) ?>">
                </div>
            </div>
            <label for="meta-description">Meta açıklama</label>
            <textarea id="meta-description" name="content[site][meta][description]"><?= e($content['site']['meta']['description'] ?? '') ?></textarea>
            <label for="og-title">OG başlık</label>
            <input type="text" id="og-title" name="content[site][meta][og_title]" value="<?= e($content['site']['meta']['og_title'] ?? '') ?>">
            <label for="og-description">OG açıklama</label>
            <textarea id="og-description" name="content[site][meta][og_description]"><?= e($content['site']['meta']['og_description'] ?? '') ?></textarea>
        </section>

        <section class="admin-card" id="sections">
            <h2>Bölüm Görünürlüğü</h2>
            <p class="admin-muted">Kapalı bölümler ön yüzde ve menüde görünmez.</p>
            <?php foreach ($sectionLabels as $sid => $label): ?>
                <label class="admin-check">
                    <input type="checkbox" name="content[site][sections][<?= e($sid) ?>][visible]" value="1"
                        <?= section_visible($content, $sid) ? 'checked' : '' ?>>
                    <?= e($label) ?>
                </label>
            <?php endforeach; ?>
        </section>

        <section class="admin-card" id="hero">
            <h2>Hero</h2>
            <label for="hero-company">Şirket adı</label>
            <input type="text" id="hero-company" name="content[hero][company]" value="<?= e($content['hero']['company']) ?>">
            <label for="hero-tagline">Slogan</label>
            <input type="text" id="hero-tagline" name="content[hero][tagline]" value="<?= e($content['hero']['tagline']) ?>">
            <label for="hero-description">Açıklama</label>
            <textarea id="hero-description" name="content[hero][description]"><?= e($content['hero']['description']) ?></textarea>
        </section>

        <section class="admin-card" id="intro">
            <h2>Kısa Tanıtım</h2>
            <label for="intro-title">Başlık</label>
            <input type="text" id="intro-title" name="content[intro][title]" value="<?= e($content['intro']['title']) ?>">
            <label for="intro-text">Metin</label>
            <textarea id="intro-text" name="content[intro][text]"><?= e($content['intro']['text']) ?></textarea>
            <h3>Rozetler</h3>
            <?php foreach ($content['intro']['badges'] as $i => $badge): ?>
                <div class="admin-grid-2">
                    <div>
                        <label>İkon</label>
                        <select name="content[intro][badges][<?= $i ?>][icon]">
                            <?php foreach ($badgeIcons as $icon): ?>
                                <option value="<?= e($icon) ?>" <?= $badge['icon'] === $icon ? 'selected' : '' ?>><?= e($icon) ?></option>
                            <?php endforeach; ?>
                        </select>
                    </div>
                    <div>
                        <label>Etiket</label>
                        <input type="text" name="content[intro][badges][<?= $i ?>][label]" value="<?= e($badge['label']) ?>">
                    </div>
                </div>
            <?php endforeach; ?>
        </section>

        <section class="admin-card" id="about">
            <h2>Hakkımızda</h2>
            <label for="about-title">Bölüm başlığı</label>
            <input type="text" id="about-title" name="content[about][title]" value="<?= e($content['about']['title']) ?>">
            <label for="about-heading">Alt başlık</label>
            <input type="text" id="about-heading" name="content[about][heading]" value="<?= e($content['about']['heading']) ?>">
            <?php foreach ($content['about']['paragraphs'] as $i => $paragraph): ?>
                <label>Paragraf <?= $i + 1 ?></label>
                <textarea name="content[about][paragraphs][<?= $i ?>]"><?= e($paragraph) ?></textarea>
            <?php endforeach; ?>
            <h3>Vizyon</h3>
            <input type="text" name="content[vision][title]" value="<?= e($content['vision']['title']) ?>">
            <textarea name="content[vision][text]"><?= e($content['vision']['text']) ?></textarea>
            <h3>Misyon</h3>
            <input type="text" name="content[mission][title]" value="<?= e($content['mission']['title']) ?>">
            <textarea name="content[mission][text]"><?= e($content['mission']['text']) ?></textarea>
        </section>

        <section class="admin-card" id="services">
            <h2>Hizmetler</h2>
            <label for="services-title">Bölüm başlığı</label>
            <input type="text" id="services-title" name="content[services][title]" value="<?= e($content['services']['title']) ?>">
            <div id="services-list" data-sortable-prefix="content[services][items]">
                <?php foreach ($content['services']['items'] as $i => $service): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Kart <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <button type="button" class="admin-btn admin-btn--danger" data-remove-item>Sil</button>
                            </div>
                        </div>
                        <label>İkon</label>
                        <select name="content[services][items][<?= $i ?>][icon]">
                            <?php foreach ($serviceIcons as $icon): ?>
                                <option value="<?= e($icon) ?>" <?= $service['icon'] === $icon ? 'selected' : '' ?>><?= e($icon) ?></option>
                            <?php endforeach; ?>
                        </select>
                        <label>Başlık</label>
                        <input type="text" name="content[services][items][<?= $i ?>][title]" value="<?= e($service['title']) ?>">
                        <label>Açıklama</label>
                        <textarea name="content[services][items][<?= $i ?>][description]"><?= e($service['description']) ?></textarea>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-service>Hizmet Ekle</button>
        </section>

        <section class="admin-card" id="team">
            <h2>Ekibimiz</h2>
            <label for="team-title">Bölüm başlığı</label>
            <input type="text" id="team-title" name="content[team][title]" value="<?= e($content['team']['title']) ?>">
            <label for="team-intro">Giriş metni</label>
            <textarea id="team-intro" name="content[team][intro]"><?= e($content['team']['intro']) ?></textarea>
            <div id="team-list" data-sortable-prefix="content[team][members]">
                <?php foreach ($content['team']['members'] as $i => $member): ?>
                    <div class="admin-list-item" data-sortable-item>
                        <div class="admin-list-item__head">
                            <strong data-item-label>Üye <?= $i + 1 ?></strong>
                            <div class="admin-actions-row">
                                <button type="button" class="admin-btn" data-sort-up>↑</button>
                                <button type="button" class="admin-btn" data-sort-down>↓</button>
                                <form method="post" action="/admin/actions.php" onsubmit="return confirm('Bu ekip üyesini silmek istediğinize emin misiniz?');">
                                    <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                                    <input type="hidden" name="action" value="delete_team_member">
                                    <input type="hidden" name="member_index" value="<?= $i ?>">
                                    <button type="submit" class="admin-btn admin-btn--danger" data-delete-team-member>Sil</button>
                                </form>
                            </div>
                        </div>
                        <input type="hidden" name="content[team][members][<?= $i ?>][photo]" value="<?= e($member['photo'] ?? '') ?>">
                        <label>Ad Soyad</label>
                        <input type="text" name="content[team][members][<?= $i ?>][name]" value="<?= e($member['name']) ?>">
                        <label>Ünvan</label>
                        <input type="text" name="content[team][members][<?= $i ?>][title]" value="<?= e($member['title']) ?>">
                        <label>Açıklama</label>
                        <textarea name="content[team][members][<?= $i ?>][description]"><?= e($member['description']) ?></textarea>
                        <?php if (!empty($member['photo'])): ?>
                            <img src="<?= e($member['photo']) ?>" alt="" class="admin-photo-preview">
                        <?php endif; ?>
                    </div>
                <?php endforeach; ?>
            </div>
            <button type="button" class="admin-btn admin-btn--gold" data-add-team>Üye Ekle</button>
        </section>

        <section class="admin-card" id="contact">
            <h2>İletişim</h2>
            <label for="contact-title">Bölüm başlığı</label>
            <input type="text" id="contact-title" name="content[contact][title]" value="<?= e($content['contact']['title']) ?>">
            <label for="contact-heading">Alt başlık</label>
            <input type="text" id="contact-heading" name="content[contact][heading]" value="<?= e($content['contact']['heading']) ?>">
            <label for="contact-email">E-posta</label>
            <input type="email" id="contact-email" name="content[contact][email]" value="<?= e($content['contact']['email']) ?>">
            <?php foreach ($content['contact']['addresses'] as $i => $address): ?>
                <h3>Adres <?= $i + 1 ?></h3>
                <input type="text" name="content[contact][addresses][<?= $i ?>][label]" value="<?= e($address['label']) ?>">
                <textarea name="content[contact][addresses][<?= $i ?>][text]"><?= e($address['text']) ?></textarea>
            <?php endforeach; ?>
            <h3>Form metinleri</h3>
            <?php foreach (['name', 'email', 'phone', 'subject', 'message'] as $field): ?>
                <label><?= e($content['contact']['form'][$field]['label']) ?></label>
                <input type="text" name="content[contact][form][<?= $field ?>][label]" value="<?= e($content['contact']['form'][$field]['label']) ?>">
                <input type="text" name="content[contact][form][<?= $field ?>][placeholder]" value="<?= e($content['contact']['form'][$field]['placeholder']) ?>">
            <?php endforeach; ?>
            <label>Gönder butonu</label>
            <input type="text" name="content[contact][form][submit]" value="<?= e($content['contact']['form']['submit']) ?>">
            <label>Başarı mesajı</label>
            <input type="text" name="content[contact][form][success]" value="<?= e($content['contact']['form']['success']) ?>">
            <label>Hata mesajı</label>
            <input type="text" name="content[contact][form][error]" value="<?= e($content['contact']['form']['error']) ?>">
        </section>

        <section class="admin-card" id="kvkk">
            <h2>KVKK</h2>
            <label for="kvkk-title">Sayfa başlığı</label>
            <input type="text" id="kvkk-title" name="content[kvkk][title]" value="<?= e($content['kvkk']['title']) ?>">
            <label for="kvkk-intro">Giriş</label>
            <textarea id="kvkk-intro" name="content[kvkk][intro]"><?= e($content['kvkk']['intro']) ?></textarea>
            <?php foreach ($content['kvkk']['sections'] as $i => $section): ?>
                <h3>Bölüm <?= $i + 1 ?></h3>
                <input type="text" name="content[kvkk][sections][<?= $i ?>][heading]" value="<?= e($section['heading']) ?>">
                <?php foreach ($section['paragraphs'] as $j => $paragraph): ?>
                    <textarea name="content[kvkk][sections][<?= $i ?>][paragraphs][<?= $j ?>]"><?= e($paragraph) ?></textarea>
                <?php endforeach; ?>
            <?php endforeach; ?>
            <label for="kvkk-note">Not</label>
            <textarea id="kvkk-note" name="content[kvkk][note]"><?= e($content['kvkk']['note'] ?? '') ?></textarea>
        </section>

        <section class="admin-card" id="footer">
            <h2>Footer ve UI</h2>
            <label>Footer hızlı bağlantılar başlığı</label>
            <input type="text" name="content[footer][quick_links_title]" value="<?= e($content['footer']['quick_links_title']) ?>">
            <label>Menü CTA</label>
            <input type="text" name="content[navigation][cta][label]" value="<?= e($content['navigation']['cta']['label']) ?>">
            <?php foreach ($content['navigation']['items'] as $i => $item): ?>
                <label>Menü: <?= e($item['id']) ?></label>
                <input type="text" name="content[navigation][items][<?= $i ?>][label]" value="<?= e($item['label']) ?>">
            <?php endforeach; ?>
        </section>

        <div class="admin-sticky-save">
            <button type="submit" class="admin-btn admin-btn--primary">Tüm İçeriği Kaydet</button>
        </div>
    </form>

    <section class="admin-card" id="media">
        <h2>Görsel Yükleme</h2>
        <p class="admin-muted">Logo/amblem değişiminde mevcut dosyaların üzerine yazılmaz; yeni dosya yolu content.json'a kaydedilir.</p>

        <h3>Ekip fotoğrafı</h3>
        <?php foreach ($content['team']['members'] as $i => $member): ?>
            <div class="admin-list-item">
                <strong><?= e($member['name']) ?></strong>
                <form method="post" action="/admin/actions.php" enctype="multipart/form-data" class="admin-form">
                    <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                    <input type="hidden" name="action" value="upload_team_photo">
                    <input type="hidden" name="member_index" value="<?= $i ?>">
                    <input type="file" name="photo" accept="image/png,image/jpeg,image/webp" required>
                    <div class="admin-actions-row">
                        <button type="submit" class="admin-btn admin-btn--gold">Fotoğraf Yükle</button>
                    </div>
                </form>
                <?php if (!empty($member['photo'])): ?>
                    <form method="post" action="/admin/actions.php">
                        <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                        <input type="hidden" name="action" value="remove_team_photo">
                        <input type="hidden" name="member_index" value="<?= $i ?>">
                        <button type="submit" class="admin-btn admin-btn--danger">Fotoğrafı Kaldır</button>
                    </form>
                <?php endif; ?>
            </div>
        <?php endforeach; ?>

        <h3>Marka varlıkları</h3>
        <?php
        $assetFields = [
            'logo_light' => 'Logo (açık zemin)',
            'logo_dark' => 'Logo (koyu zemin)',
            'emblem' => 'Amblem (hero)',
            'favicon' => 'Favicon',
            'apple_touch_icon' => 'Apple Touch Icon',
        ];
        foreach ($assetFields as $key => $label):
            $path = $content['site']['assets'][$key] ?? '';
        ?>
            <div class="admin-list-item">
                <strong><?= e($label) ?></strong>
                <p class="admin-muted">Mevcut: <?= e($path) ?></p>
                <form method="post" action="/admin/actions.php" enctype="multipart/form-data" class="admin-form">
                    <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                    <input type="hidden" name="action" value="upload_asset">
                    <input type="hidden" name="asset_key" value="<?= e($key) ?>">
                    <input type="file" name="asset_file" accept="image/png,image/jpeg,image/webp" required>
                    <button type="submit" class="admin-btn">Yükle</button>
                </form>
            </div>
        <?php endforeach; ?>
    </section>

    <section class="admin-card" id="backups">
        <h2>Yedekler</h2>
        <p class="admin-muted">Her kayıttan önce otomatik yedek alınır (son 20).</p>
        <?php if ($backups === []): ?>
            <p class="admin-muted">Henüz yedek yok.</p>
        <?php else: ?>
            <ul class="admin-backup-list">
                <?php foreach ($backups as $backup): ?>
                    <li>
                        <span><?= e($backup['name']) ?> — <?= date('d.m.Y H:i', $backup['mtime']) ?></span>
                        <form method="post" action="/admin/actions.php">
                            <input type="hidden" name="csrf_token" value="<?= e($csrf) ?>">
                            <input type="hidden" name="action" value="restore_backup">
                            <input type="hidden" name="backup_name" value="<?= e($backup['name']) ?>">
                            <button type="submit" class="admin-btn">Geri Yükle</button>
                        </form>
                    </li>
                <?php endforeach; ?>
            </ul>
        <?php endif; ?>
    </section>
</div>

<template id="service-item-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni kart</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
                <button type="button" class="admin-btn admin-btn--danger" data-remove-item>Sil</button>
            </div>
        </div>
        <select name="content[services][items][__INDEX__][icon]">
            <?php foreach ($serviceIcons as $icon): ?>
                <option value="<?= e($icon) ?>"><?= e($icon) ?></option>
            <?php endforeach; ?>
        </select>
        <input type="text" name="content[services][items][__INDEX__][title]" placeholder="Başlık">
        <textarea name="content[services][items][__INDEX__][description]" placeholder="Açıklama"></textarea>
    </div>
</template>

<template id="team-item-template">
    <div class="admin-list-item" data-sortable-item>
        <div class="admin-list-item__head">
            <strong data-item-label>Yeni üye</strong>
            <div class="admin-actions-row">
                <button type="button" class="admin-btn" data-sort-up>↑</button>
                <button type="button" class="admin-btn" data-sort-down>↓</button>
            </div>
        </div>
        <input type="hidden" name="content[team][members][__INDEX__][photo]" value="">
        <input type="text" name="content[team][members][__INDEX__][name]" placeholder="Ad Soyad">
        <input type="text" name="content[team][members][__INDEX__][title]" placeholder="Ünvan">
        <textarea name="content[team][members][__INDEX__][description]" placeholder="Açıklama"></textarea>
    </div>
</template>

<script src="/admin/assets/admin.js" defer></script>
</body>
</html>
