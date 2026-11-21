/*

    File: file_qoi.c

    Copyright (C) 2026 Christophe GRENIER <grenier@cgsecurity.org>

    QOI - The "Quite OK Image" format
    https://qoiformat.org/qoi-specification.pdf

    This software is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write the Free Software Foundation, Inc., 51
    Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

 */

#if !defined(SINGLE_FORMAT) || defined(SINGLE_FORMAT_qoi)
#ifdef HAVE_CONFIG_H
#include <config.h>
#endif
#ifdef HAVE_STRING_H
#include <string.h>
#endif
#include <stdio.h>
#include "types.h"
#include "common.h"
#include "filegen.h"

/*@ requires valid_register_header_check(file_stat); */
static void register_header_check_qoi(file_stat_t *file_stat);

const file_hint_t file_hint_qoi = {
  .extension = "qoi",
  .description = "Quite OK Image",
  .max_filesize = PHOTOREC_MAX_FILE_SIZE,
  .recover = 1,
  .enable_by_default = 1,
  .register_header_check = &register_header_check_qoi
};

/*@
  @ requires file_recovery->file_check == &file_check_qoi;
  @ requires valid_file_check_param(file_recovery);
  @ ensures  valid_file_check_result(file_recovery);
  @ assigns *file_recovery->handle, errno, file_recovery->file_size;
  @ assigns Frama_C_entropy_source;
  @*/
static void file_check_qoi(file_recovery_t *file_recovery)
{
  static const unsigned char qoi_footer[8] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
  };
  file_search_footer(file_recovery, qoi_footer, sizeof(qoi_footer), 0);
}

/*@
  @ requires buffer_size >= 14;
  @ requires separation: \separated(&file_hint_qoi, buffer+(..), file_recovery, file_recovery_new);
  @ requires valid_header_check_param(buffer, buffer_size, safe_header_only, file_recovery, file_recovery_new);
  @ ensures  valid_header_check_result(\result, file_recovery_new);
  @ assigns  *file_recovery_new;
  @*/
static int header_check_qoi(const unsigned char *buffer, const unsigned int buffer_size, const unsigned int safe_header_only, const file_recovery_t *file_recovery, file_recovery_t *file_recovery_new)
{
  const uint32_t width = be32(*(const uint32_t *)(buffer + 4));
  const uint32_t height = be32(*(const uint32_t *)(buffer + 8));
  const unsigned char channels = buffer[12];
  const unsigned char colorspace = buffer[13];
  if(width == 0 || height == 0)
    return 0;
  if(channels != 3 && channels != 4)
    return 0;
  if(colorspace > 1)
    return 0;
  reset_file_recovery(file_recovery_new);
  file_recovery_new->file_check = &file_check_qoi;
  file_recovery_new->extension = file_hint_qoi.extension;
  return 1;
}

static void register_header_check_qoi(file_stat_t *file_stat)
{
  static const unsigned char qoi_header[4] = {
    'q', 'o', 'i', 'f'
  };
  register_header_check(0, qoi_header, sizeof(qoi_header), &header_check_qoi, file_stat);
}
#endif
