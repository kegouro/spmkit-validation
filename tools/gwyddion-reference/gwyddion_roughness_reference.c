/* SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Headless roughness reference linked to public Gwyddion libraries.
 * The standalone initialization and loading approach was informed by the
 * upstream gwybatch example (David Necas, 2009-2019).  No SPM-Kit code is
 * used by this program.
 */

#include <errno.h>
#include <locale.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <app/gwyapp.h>
#include <libgwyddion/gwyddion.h>
#include <libgwymodule/gwymodule.h>
#include <libprocess/gwyprocess.h>

#define HELPER_VERSION "0.1.0"

enum ExitCode {
    EXIT_OK = 0,
    EXIT_USAGE = 2,
    EXIT_INPUT = 3,
    EXIT_LOAD = 4,
    EXIT_CONTRACT = 5,
};

typedef struct {
    gint requested_channel;
    const gchar *module_dir;
    const gchar *unit_z;
    const gchar *input_path;
} Options;

typedef struct {
    GArray *ids;
} ChannelInventory;

static void
print_help(void)
{
    g_print("Usage: spmkit-gwyddion-roughness-reference "
            "[--channel N] --module-dir DIR --unit-z UNIT INPUT\n"
            "Load one file with Gwyddion libraries and emit strict JSON roughness.\n"
            "No leveling, filtering, masking, or ROI reduction is applied.\n");
}

static gboolean
parse_nonnegative_int(const gchar *text, gint *value)
{
    gchar *end = NULL;
    long parsed;

    errno = 0;
    parsed = strtol(text, &end, 10);
    if (errno || !end || *end || end == text || parsed < 0 || parsed > G_MAXINT)
        return FALSE;
    *value = (gint)parsed;
    return TRUE;
}

static gboolean
unit_is_safe(const gchar *unit)
{
    const guchar *p = (const guchar*)unit;

    if (!*p)
        return FALSE;
    for (; *p; p++) {
        if (!(g_ascii_isalnum(*p)
              || *p == ' ' || *p == '*' || *p == '/' || *p == '^'
              || *p == '-' || *p == '.' || *p == '_'))
            return FALSE;
    }
    return TRUE;
}

static gboolean
parse_options(int argc, char **argv, Options *options)
{
    gint i;

    options->requested_channel = -1;
    options->module_dir = NULL;
    options->unit_z = NULL;
    options->input_path = NULL;

    for (i = 1; i < argc; i++) {
        if (gwy_strequal(argv[i], "--channel")) {
            if (++i >= argc || !parse_nonnegative_int(argv[i], &options->requested_channel)) {
                g_printerr("invalid --channel value\n");
                return FALSE;
            }
        }
        else if (gwy_strequal(argv[i], "--module-dir")) {
            if (++i >= argc || !g_file_test(argv[i], G_FILE_TEST_IS_DIR)) {
                g_printerr("invalid --module-dir value\n");
                return FALSE;
            }
            options->module_dir = argv[i];
        }
        else if (gwy_strequal(argv[i], "--unit-z")) {
            if (++i >= argc || !unit_is_safe(argv[i])) {
                g_printerr("invalid --unit-z value\n");
                return FALSE;
            }
            options->unit_z = argv[i];
        }
        else if (argv[i][0] == '-') {
            g_printerr("unknown option: %s\n", argv[i]);
            return FALSE;
        }
        else if (options->input_path) {
            g_printerr("exactly one input file is required\n");
            return FALSE;
        }
        else {
            options->input_path = argv[i];
        }
    }

    if (!options->module_dir || !options->unit_z || !options->input_path) {
        g_printerr("--module-dir, --unit-z and one input file are required\n");
        return FALSE;
    }
    return TRUE;
}

static gchar*
sha256_file(const gchar *path, GError **error)
{
    GChecksum *checksum;
    FILE *stream;
    guchar buffer[65536];
    size_t count;
    gchar *digest = NULL;

    stream = fopen(path, "rb");
    if (!stream) {
        g_set_error(error,
                    G_FILE_ERROR,
                    g_file_error_from_errno(errno),
                    "cannot open input: %s",
                    g_strerror(errno));
        return NULL;
    }
    checksum = g_checksum_new(G_CHECKSUM_SHA256);
    while ((count = fread(buffer, 1, sizeof(buffer), stream)) > 0)
        g_checksum_update(checksum, buffer, count);
    if (ferror(stream)) {
        g_set_error(error,
                    G_FILE_ERROR,
                    g_file_error_from_errno(errno),
                    "cannot read input: %s",
                    g_strerror(errno));
    }
    else {
        digest = g_strdup(g_checksum_get_string(checksum));
    }
    if (fclose(stream) != 0 && digest) {
        g_free(digest);
        digest = NULL;
        g_set_error(error,
                    G_FILE_ERROR,
                    g_file_error_from_errno(errno),
                    "cannot close input: %s",
                    g_strerror(errno));
    }
    g_checksum_free(checksum);
    return digest;
}

static gboolean
contains_id(const GArray *ids, gint id)
{
    guint i;

    for (i = 0; i < ids->len; i++) {
        if (g_array_index(ids, gint, i) == id)
            return TRUE;
    }
    return FALSE;
}

static void
collect_channel(gpointer pquark, gpointer pvalue, gpointer user_data)
{
    const gchar *key = g_quark_to_string(GPOINTER_TO_UINT(pquark));
    GValue *value = (GValue*)pvalue;
    ChannelInventory *inventory = (ChannelInventory*)user_data;
    gchar *end = NULL;
    long id;

    if (!key || key[0] != '/' || !G_VALUE_HOLDS_OBJECT(value))
        return;
    if (!g_type_is_a(G_TYPE_FROM_INSTANCE(g_value_get_object(value)), GWY_TYPE_DATA_FIELD))
        return;
    errno = 0;
    id = strtol(key + 1, &end, 10);
    if (errno || end == key + 1 || id < 0 || id > G_MAXINT || !gwy_strequal(end, "/data"))
        return;
    if (!contains_id(inventory->ids, (gint)id)) {
        gint converted = (gint)id;
        g_array_append_val(inventory->ids, converted);
    }
}

static gint
select_channel(GwyContainer *container, gint requested_channel, GArray **ids_out)
{
    ChannelInventory inventory;
    guint i;

    inventory.ids = g_array_new(FALSE, FALSE, sizeof(gint));
    gwy_container_foreach(container, NULL, collect_channel, &inventory);
    *ids_out = inventory.ids;
    if (!inventory.ids->len)
        return -1;
    if (requested_channel < 0)
        return inventory.ids->len == 1 ? g_array_index(inventory.ids, gint, 0) : -2;
    for (i = 0; i < inventory.ids->len; i++) {
        if (g_array_index(inventory.ids, gint, i) == requested_channel)
            return requested_channel;
    }
    return -3;
}

static gboolean
field_is_finite(GwyDataField *field)
{
    const gdouble *data = gwy_data_field_get_data_const(field);
    gint i;
    gint n = gwy_data_field_get_xres(field) * gwy_data_field_get_yres(field);

    for (i = 0; i < n; i++) {
        if (!isfinite(data[i]))
            return FALSE;
    }
    return TRUE;
}

static gdouble
calculate_sa(GwyDataField *field, gdouble mean)
{
    const gdouble *data = gwy_data_field_get_data_const(field);
    gdouble sum = 0.0;
    gint i;
    gint n = gwy_data_field_get_xres(field) * gwy_data_field_get_yres(field);

    for (i = 0; i < n; i++)
        sum += fabs(data[i] - mean);
    return sum/n;
}

int
main(int argc, char **argv)
{
    Options options;
    gchar *file_module_dir;
    const gchar *module_dirs[2];
    GError *error = NULL;
    GwyContainer *container;
    GwyDataField *field;
    GArray *channel_ids = NULL;
    gchar *input_sha256;
    gchar *unit_z;
    gchar data_key[64];
    gdouble mean, sa, sq, min, max, sz;
    gint channel, rows, columns;

    if (!setlocale(LC_ALL, "C")) {
        g_printerr("cannot set C locale\n");
        return EXIT_CONTRACT;
    }
    g_setenv("LC_ALL", "C", TRUE);
    g_setenv("LANG", "C", TRUE);

    if (argc == 2 && gwy_strequal(argv[1], "--help")) {
        print_help();
        return EXIT_OK;
    }
    if (argc == 2 && gwy_strequal(argv[1], "--version")) {
        g_print("spmkit-gwyddion-roughness-reference %s (Gwyddion %s)\n",
                HELPER_VERSION,
                gwy_version_string());
        return EXIT_OK;
    }
    if (!parse_options(argc, argv, &options)) {
        print_help();
        return EXIT_USAGE;
    }

    input_sha256 = sha256_file(options.input_path, &error);
    if (!input_sha256) {
        g_printerr("input error: %s\n", error ? error->message : "unknown error");
        g_clear_error(&error);
        return EXIT_INPUT;
    }

    file_module_dir = g_build_filename(options.module_dir, "file", NULL);
    module_dirs[0] = file_module_dir;
    module_dirs[1] = NULL;
    gwy_widgets_type_init();
    gwy_module_disable_registration("plugin-proxy");
    gwy_module_disable_registration("pygwy");
    gwy_threads_set_enabled(FALSE);
    gwy_module_register_modules(module_dirs);

    container = gwy_file_load(options.input_path, GWY_RUN_NONINTERACTIVE, &error);
    g_free(file_module_dir);
    if (!container) {
        g_printerr("Gwyddion load failed: %s\n", error ? error->message : "unknown error");
        g_clear_error(&error);
        g_free(input_sha256);
        return EXIT_LOAD;
    }

    channel = select_channel(container, options.requested_channel, &channel_ids);
    if (channel == -1) {
        g_printerr("input contains no Gwyddion data channel\n");
    }
    else if (channel == -2) {
        g_printerr("input contains %u channels; --channel is required\n", channel_ids->len);
    }
    else if (channel == -3) {
        g_printerr("requested channel %d does not exist\n", options.requested_channel);
    }
    if (channel < 0) {
        g_array_free(channel_ids, TRUE);
        g_object_unref(container);
        g_free(input_sha256);
        return EXIT_CONTRACT;
    }
    g_array_free(channel_ids, TRUE);

    g_snprintf(data_key, sizeof(data_key), "/%d/data", channel);
    field = GWY_DATA_FIELD(gwy_container_get_object_by_name(container, data_key));
    if (!field || !field_is_finite(field)) {
        g_printerr("selected channel is missing or contains NaN/Infinity\n");
        g_object_unref(container);
        g_free(input_sha256);
        return EXIT_CONTRACT;
    }

    unit_z = gwy_si_unit_get_string(
        gwy_data_field_get_si_unit_z(field), GWY_SI_UNIT_FORMAT_PLAIN
    );
    if (!unit_z || !gwy_strequal(unit_z, options.unit_z)) {
        g_printerr("Gwyddion data-field unit does not match --unit-z\n");
        g_free(unit_z);
        g_object_unref(container);
        g_free(input_sha256);
        return EXIT_CONTRACT;
    }

    mean = gwy_data_field_get_avg(field);
    sa = calculate_sa(field, mean);
    sq = gwy_data_field_get_rms(field);
    gwy_data_field_get_min_max(field, &min, &max);
    sz = max - min;
    if (!(isfinite(mean) && isfinite(sa) && isfinite(sq)
          && isfinite(min) && isfinite(max) && isfinite(sz))) {
        g_printerr("computed statistics are not finite\n");
        g_free(unit_z);
        g_object_unref(container);
        g_free(input_sha256);
        return EXIT_CONTRACT;
    }

    rows = gwy_data_field_get_yres(field);
    columns = gwy_data_field_get_xres(field);
    g_print("{\"schema\":\"spmkit-gwyddion-reference-output/0.1.0\","
            "\"status\":\"COMPLETED\",\"producer\":\"Gwyddion libraries\","
            "\"gwyddion_version\":\"%s\",\"helper_version\":\"%s\","
            "\"input_sha256\":\"%s\",\"channel\":%d,"
            "\"shape\":[%d,%d],\"axis_order\":\"ROW_Y_COLUMN_X\","
            "\"unit_z\":\"%s\",\"unit_source\":\"GWYDDION_DATA_FIELD\","
            "\"preprocessing\":{\"leveling\":\"NONE\","
            "\"filtering\":\"NONE\",\"masking\":\"NONE\"," 
            "\"roi\":\"FULL_FIELD\"},\"mean\":%.17g,\"Sa\":%.17g,"
            "\"Sq\":%.17g,\"min\":%.17g,\"max\":%.17g,\"Sz\":%.17g}\n",
            gwy_version_string(), HELPER_VERSION, input_sha256, channel,
            rows, columns, unit_z, mean, sa, sq, min, max, sz);

    g_free(unit_z);
    g_object_unref(container);
    g_free(input_sha256);
    return EXIT_OK;
}
