<?php
declare(strict_types=1);

require_once __DIR__ . '/content_store.php';

/**
 * Admin panel etkin dil (tr|en|de|ru|fa).
 */
function admin_resolve_lang(): string
{
    if (array_key_exists('admin_lang', $_GET)) {
        $requested = strtolower(trim((string) ($_GET['admin_lang'] ?? '')));
        if (is_supported_site_lang($requested)) {
            admin_start_session();
            $_SESSION['admin_edit_lang'] = $requested;
            return $requested;
        }
    }

    admin_start_session();
    $sessionLang = strtolower(trim((string) ($_SESSION['admin_edit_lang'] ?? '')));
    if (is_supported_site_lang($sessionLang)) {
        return $sessionLang;
    }

    return SITE_LANG_DEFAULT;
}

function admin_resolve_lang_from_post(): string
{
    $posted = strtolower(trim((string) ($_POST['admin_lang'] ?? '')));
    if (is_supported_site_lang($posted)) {
        return $posted;
    }

    return admin_resolve_lang();
}

function admin_is_tr_mode(string $lang): bool
{
    return $lang === SITE_LANG_DEFAULT;
}

function admin_require_tr_mode(string $lang): void
{
    if (!admin_is_tr_mode($lang)) {
        http_response_code(403);
        header('Content-Type: text/plain; charset=UTF-8');
        echo 'Yapısal işlemler yalnızca TR modunda yapılabilir.';
        exit;
    }
}

function admin_dashboard_url(string $lang, string $fragment = ''): string
{
    $url = '/admin/dashboard.php';
    if ($lang !== SITE_LANG_DEFAULT) {
        $url .= '?admin_lang=' . rawurlencode($lang);
    }
    if ($fragment !== '') {
        $url .= '#' . ltrim($fragment, '#');
    }

    return $url;
}

function admin_load_lang_file(string $lang): array
{
    $path = content_file_path_for_lang($lang);
    if (!is_readable($path)) {
        throw new RuntimeException('İçerik dosyası okunamadı: ' . $lang);
    }
    $data = load_content_file($path);
    if ($data === []) {
        throw new RuntimeException('Geçersiz içerik formatı: ' . $lang);
    }
    $data['site']['lang'] = $lang;

    return $data;
}

function admin_load_all_lang_files(): array
{
    $out = [];
    foreach (SITE_LANGS as $lang) {
        $out[$lang] = admin_load_lang_file($lang);
    }

    return $out;
}

/**
 * TR kaynaklı dil-bağımsız alanları hedef içeriğe uygula.
 */
function admin_apply_lang_independent_from_tr(array $target, array $tr): array
{
    $target['site']['url'] = $tr['site']['url'] ?? $target['site']['url'] ?? '';
    if (isset($tr['site']['assets']) && is_array($tr['site']['assets'])) {
        $target['site']['assets'] = $tr['site']['assets'];
    }
    if (isset($tr['site']['sections']) && is_array($tr['site']['sections'])) {
        $target['site']['sections'] = $tr['site']['sections'];
    }
    if (isset($tr['site']['meta']['og_image'])) {
        $target['site']['meta']['og_image'] = $tr['site']['meta']['og_image'];
    }
    if (isset($tr['display']) && is_array($tr['display'])) {
        $target['display'] = $tr['display'];
    }
    $target['hero']['watermark_enabled'] = $tr['hero']['watermark_enabled'] ?? false;
    $target['contact']['email'] = $tr['contact']['email'] ?? '';

    $trServices = $tr['services']['items'] ?? [];
    $targetServices = $target['services']['items'] ?? [];
    foreach ($trServices as $i => $trItem) {
        if (!isset($targetServices[$i]) || !is_array($targetServices[$i])) {
            continue;
        }
        $targetServices[$i]['icon'] = $trItem['icon'] ?? $targetServices[$i]['icon'] ?? '';
    }
    $target['services']['items'] = $targetServices;

    $trBadges = $tr['intro']['badges'] ?? [];
    $targetBadges = $target['intro']['badges'] ?? [];
    foreach ($trBadges as $i => $trBadge) {
        if (!isset($targetBadges[$i]) || !is_array($targetBadges[$i])) {
            continue;
        }
        $targetBadges[$i]['icon'] = $trBadge['icon'] ?? $targetBadges[$i]['icon'] ?? '';
    }
    $target['intro']['badges'] = $targetBadges;

    $trMembers = $tr['team']['members'] ?? [];
    $targetMembers = $target['team']['members'] ?? [];
    foreach ($trMembers as $i => $trMember) {
        if (!isset($targetMembers[$i]) || !is_array($targetMembers[$i])) {
            continue;
        }
        $targetMembers[$i]['photo'] = $trMember['photo'] ?? '';
    }
    $target['team']['members'] = $targetMembers;

    $trInfo = $tr['contact']['info_items'] ?? [];
    $targetInfo = $target['contact']['info_items'] ?? [];
    foreach ($trInfo as $i => $trItem) {
        if (!isset($targetInfo[$i]) || !is_array($targetInfo[$i])) {
            continue;
        }
        $targetInfo[$i]['type'] = $trItem['type'] ?? $targetInfo[$i]['type'] ?? '';
        $targetInfo[$i]['value'] = $trItem['value'] ?? '';
    }
    $target['contact']['info_items'] = $targetInfo;

    $trAddresses = $tr['contact']['addresses'] ?? [];
    $targetAddresses = $target['contact']['addresses'] ?? [];
    foreach ($trAddresses as $i => $trAddr) {
        if (!isset($targetAddresses[$i]) || !is_array($targetAddresses[$i])) {
            continue;
        }
        $targetAddresses[$i]['text'] = $trAddr['text'] ?? '';
    }
    $target['contact']['addresses'] = $targetAddresses;

    $trNav = $tr['navigation']['items'] ?? [];
    $targetNav = $target['navigation']['items'] ?? [];
    foreach ($trNav as $i => $trItem) {
        if (!isset($targetNav[$i]) || !is_array($targetNav[$i])) {
            continue;
        }
        $targetNav[$i]['id'] = $trItem['id'] ?? $targetNav[$i]['id'] ?? '';
        $targetNav[$i]['href'] = $trItem['href'] ?? $targetNav[$i]['href'] ?? '';
    }
    $target['navigation']['items'] = $targetNav;
    if (isset($tr['navigation']['cta']['href'])) {
        $target['navigation']['cta']['href'] = $tr['navigation']['cta']['href'];
    }

    return $target;
}

/**
 * TR yapısını tüm çeviri dillere yansıt; yeni öğeler TR metniyle tohumlanır.
 */
function admin_sync_structure_from_tr(array $tr, array $localized): array
{
    $localized['intro']['badges'] = admin_sync_badge_list(
        $tr['intro']['badges'] ?? [],
        $localized['intro']['badges'] ?? []
    );

    $localized['services']['items'] = admin_sync_service_list(
        $tr['services']['items'] ?? [],
        $localized['services']['items'] ?? []
    );

    $localized['process']['steps'] = admin_sync_step_list(
        $tr['process']['steps'] ?? [],
        $localized['process']['steps'] ?? []
    );

    $localized['team']['members'] = admin_sync_member_list(
        $tr['team']['members'] ?? [],
        $localized['team']['members'] ?? []
    );

    $localized['contact']['info_items'] = admin_sync_info_items(
        $tr['contact']['info_items'] ?? [],
        $localized['contact']['info_items'] ?? []
    );

    $localized['contact']['addresses'] = admin_sync_addresses(
        $tr['contact']['addresses'] ?? [],
        $localized['contact']['addresses'] ?? []
    );

    if (isset($tr['contact']['hours']) && is_array($tr['contact']['hours'])) {
        $localized['contact']['hours'] = admin_sync_hours(
            $tr['contact']['hours'],
            $localized['contact']['hours'] ?? null
        );
    } elseif (array_key_exists('hours', $tr['contact'] ?? [])) {
        unset($localized['contact']['hours']);
    }

    $localized['about']['paragraphs'] = admin_sync_string_list(
        $tr['about']['paragraphs'] ?? [],
        $localized['about']['paragraphs'] ?? []
    );

    $localized['navigation']['items'] = admin_sync_nav_items(
        $tr['navigation']['items'] ?? [],
        $localized['navigation']['items'] ?? []
    );

    $localized['kvkk']['sections'] = admin_sync_kvkk_sections(
        $tr['kvkk']['sections'] ?? [],
        $localized['kvkk']['sections'] ?? []
    );

    return admin_apply_lang_independent_from_tr($localized, $tr);
}

function admin_sync_string_list(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trText) {
        $result[] = isset($locList[$i]) && is_string($locList[$i]) && trim($locList[$i]) !== ''
            ? $locList[$i]
            : $trText;
    }

    return $result;
}

function admin_sync_badge_list(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'icon' => $trItem['icon'] ?? 'energy',
            'label' => (is_array($locItem) && trim((string) ($locItem['label'] ?? '')) !== '')
                ? $locItem['label']
                : ($trItem['label'] ?? ''),
        ];
    }

    return $result;
}

function admin_sync_service_list(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'icon' => $trItem['icon'] ?? 'strategy',
            'title' => (is_array($locItem) && trim((string) ($locItem['title'] ?? '')) !== '')
                ? $locItem['title']
                : ($trItem['title'] ?? ''),
            'description' => (is_array($locItem) && trim((string) ($locItem['description'] ?? '')) !== '')
                ? $locItem['description']
                : ($trItem['description'] ?? ''),
        ];
    }

    return $result;
}

function admin_sync_step_list(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'title' => (is_array($locItem) && trim((string) ($locItem['title'] ?? '')) !== '')
                ? $locItem['title']
                : ($trItem['title'] ?? ''),
            'description' => (is_array($locItem) && trim((string) ($locItem['description'] ?? '')) !== '')
                ? $locItem['description']
                : ($trItem['description'] ?? ''),
        ];
    }

    return $result;
}

function admin_sync_member_list(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'photo' => $trItem['photo'] ?? '',
            'name' => (is_array($locItem) && trim((string) ($locItem['name'] ?? '')) !== '')
                ? $locItem['name']
                : ($trItem['name'] ?? ''),
            'title' => (is_array($locItem) && trim((string) ($locItem['title'] ?? '')) !== '')
                ? $locItem['title']
                : ($trItem['title'] ?? ''),
            'description' => (is_array($locItem) && trim((string) ($locItem['description'] ?? '')) !== '')
                ? $locItem['description']
                : ($trItem['description'] ?? ''),
        ];
    }

    return $result;
}

function admin_sync_info_items(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'type' => $trItem['type'] ?? '',
            'title' => (is_array($locItem) && trim((string) ($locItem['title'] ?? '')) !== '')
                ? $locItem['title']
                : ($trItem['title'] ?? ''),
            'value' => $trItem['value'] ?? '',
        ];
    }

    return $result;
}

function admin_sync_addresses(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'label' => (is_array($locItem) && trim((string) ($locItem['label'] ?? '')) !== '')
                ? $locItem['label']
                : ($trItem['label'] ?? ''),
            'text' => $trItem['text'] ?? '',
        ];
    }

    return $result;
}

function admin_sync_hours(array $trHours, ?array $locHours): array
{
    $trRows = $trHours['rows'] ?? [];
    $locRows = is_array($locHours) ? ($locHours['rows'] ?? []) : [];
    $rows = [];
    foreach ($trRows as $i => $trRow) {
        $locRow = $locRows[$i] ?? null;
        $rows[] = [
            'label' => (is_array($locRow) && trim((string) ($locRow['label'] ?? '')) !== '')
                ? $locRow['label']
                : ($trRow['label'] ?? ''),
            'value' => (is_array($locRow) && trim((string) ($locRow['value'] ?? '')) !== '')
                ? $locRow['value']
                : ($trRow['value'] ?? ''),
        ];
    }

    $title = is_array($locHours) && trim((string) ($locHours['title'] ?? '')) !== ''
        ? $locHours['title']
        : ($trHours['title'] ?? '');

    return ['title' => $title, 'rows' => $rows];
}

function admin_sync_nav_items(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trItem) {
        $locItem = $locList[$i] ?? null;
        $result[] = [
            'id' => $trItem['id'] ?? '',
            'href' => $trItem['href'] ?? '',
            'label' => (is_array($locItem) && trim((string) ($locItem['label'] ?? '')) !== '')
                ? $locItem['label']
                : ($trItem['label'] ?? ''),
        ];
    }

    return $result;
}

function admin_sync_kvkk_sections(array $trList, array $locList): array
{
    $result = [];
    foreach ($trList as $i => $trSection) {
        $locSection = $locList[$i] ?? null;
        $trParagraphs = $trSection['paragraphs'] ?? [];
        $locParagraphs = is_array($locSection) ? ($locSection['paragraphs'] ?? []) : [];
        $result[] = [
            'heading' => (is_array($locSection) && trim((string) ($locSection['heading'] ?? '')) !== '')
                ? $locSection['heading']
                : ($trSection['heading'] ?? ''),
            'paragraphs' => admin_sync_string_list($trParagraphs, $locParagraphs),
        ];
    }

    return $result;
}

/**
 * TR yapısal kayıt: TR + tüm çeviri dillerinde yapı senkronu.
 */
function admin_save_tr_with_structure_sync(array $trContent): bool
{
    $all = admin_load_all_lang_files();
    $all['tr'] = $trContent;
    $all['tr']['site']['lang'] = SITE_LANG_DEFAULT;

    foreach (SITE_LANGS as $lang) {
        if ($lang === SITE_LANG_DEFAULT) {
            continue;
        }
        $all[$lang] = admin_sync_structure_from_tr($all['tr'], $all[$lang]);
        $all[$lang]['site']['lang'] = $lang;
    }

    if (!save_content_for_lang('tr', $all['tr'], true)) {
        return false;
    }

    foreach (SITE_LANGS as $lang) {
        if ($lang === SITE_LANG_DEFAULT) {
            continue;
        }
        if (!save_content_for_lang($lang, $all[$lang], false)) {
            return false;
        }
    }

    return true;
}

/**
 * Dil-bağımsız alan güncellemesi (medya vb.) — tüm dil dosyalarında senkron.
 */
function admin_save_tr_lang_independent_sync(array $trContent): bool
{
    $all = admin_load_all_lang_files();
    $all['tr'] = $trContent;
    $all['tr']['site']['lang'] = SITE_LANG_DEFAULT;

    foreach (SITE_LANGS as $lang) {
        if ($lang === SITE_LANG_DEFAULT) {
            continue;
        }
        $all[$lang] = admin_apply_lang_independent_from_tr($all[$lang], $all['tr']);
        $all[$lang]['site']['lang'] = $lang;
    }

    if (!save_content_for_lang('tr', $all['tr'], true)) {
        return false;
    }

    foreach (SITE_LANGS as $lang) {
        if ($lang === SITE_LANG_DEFAULT) {
            continue;
        }
        if (!save_content_for_lang($lang, $all[$lang], false)) {
            return false;
        }
    }

    return true;
}

/**
 * Yalnız seçili dil dosyasına kaydet (metin düzenleme).
 */
function admin_save_localized_text(string $lang, array $content): bool
{
    $all = admin_load_all_lang_files();
    $tr = $all['tr'];
    $content = admin_apply_lang_independent_from_tr($content, $tr);
    $content['site']['lang'] = $lang;

    return save_content_for_lang($lang, $content, true);
}
